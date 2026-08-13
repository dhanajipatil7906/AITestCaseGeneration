import io
import json
import os
import traceback
import uuid
from collections import Counter
from types import SimpleNamespace
from typing import Optional, Sequence, Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from openpyxl import Workbook
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, get_current_user_optional
from app.config import settings
from app.db.database import get_db
from app.models.analysis_result import AnalysisResult
from app.models.generated_test_case import GeneratedTestCase
from app.models.project import Project
from app.services.llm_test_generator import generate_module_test_cases, module_key_for_path


router = APIRouter(
    prefix="/api/analysis",
    tags=["analysis"],
)


def detect_language(filename: str) -> str:
    extension = os.path.splitext(filename)[1].lower()

    languages = {
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".java": "Java",
        ".c": "C",
        ".cpp": "C++",
        ".h": "C/C++",
        ".hpp": "C++",
        ".cs": "C#",
        ".go": "Go",
        ".rs": "Rust",
        ".php": "PHP",
        ".rb": "Ruby",
        ".swift": "Swift",
        ".kt": "Kotlin",
        ".sql": "SQL",
        ".html": "HTML",
        ".css": "CSS",
        ".json": "JSON",
        ".xml": "XML",
        ".yaml": "YAML",
        ".yml": "YAML",
    }

    return languages.get(extension, "Unknown")


def classify_project_type(files: list[dict]) -> str:
    for file_info in files:
        path = (file_info.get("path") or "").lower()
        language = (file_info.get("language") or "").lower()

        if "controller" in path or path.endswith("controller.cs"):
            return "dotnet"

        if language == "c#" and ("controllers" in path or "models" in path):
            return "dotnet"

    return "generic"


def _generate_test_cases_by_module(processed_files: list[dict]) -> list[dict]:
    """Group files by module, ask Claude for module-wise test cases, and
    attach the resulting test cases back onto each file entry."""
    modules: dict[str, list[dict]] = {}
    for file_info in processed_files:
        modules.setdefault(file_info["module"], []).append(file_info)

    modules_summary = []
    for module_name, module_files in modules.items():
        module_test_cases = generate_module_test_cases(module_name, module_files)

        test_cases_by_path: dict[str, list[str]] = {}
        for entry in module_test_cases:
            test_cases_by_path.setdefault(entry["file"], []).append(entry["test_case"])

        for file_info in module_files:
            file_info["test_cases"] = test_cases_by_path.get(file_info["path"], [])

        modules_summary.append(
            {
                "name": module_name,
                "files": [file_info["path"] for file_info in module_files],
                "test_case_count": sum(len(file_info["test_cases"]) for file_info in module_files),
            }
        )

    return modules_summary



def analyze_single_file(
    file_path: str,
    content: str,
) -> dict:
    language = detect_language(file_path)

    lines = content.splitlines()

    function_count = 0
    class_count = 0

    if language == "Python":
        for line in lines:
            stripped = line.strip()

            if stripped.startswith("def "):
                function_count += 1

            elif stripped.startswith("async def "):
                function_count += 1

            elif stripped.startswith("class "):
                class_count += 1

    elif language in {
        "JavaScript",
        "TypeScript",
        "Java",
        "C",
        "C++",
        "C#",
        "Go",
        "Rust",
        "PHP",
    }:
        for line in lines:
            stripped = line.strip()

            if (
                stripped.startswith("function ")
                or "function " in stripped
                or stripped.startswith("def ")
            ):
                function_count += 1

            if stripped.startswith("class "):
                class_count += 1

    return {
        "name": os.path.basename(file_path),
        "path": file_path,
        "language": language,
        "lines": len(lines),
        "functions": function_count,
        "classes": class_count,
    }


def _build_project_stub(name: str, path: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        path=path,
    )


def _get_or_create_project(db: Session, project_id: str | None, project_name: str | None) -> Project | SimpleNamespace:
    if project_id:
        try:
            project = db.get(Project, project_id)
            if project is not None:
                return project
        except Exception:
            pass

    folder_name = (project_name or "Imported Project").strip() or "Imported Project"
    project_path = f"memory://{folder_name.lower().replace(' ', '-')}"

    try:
        project = db.query(Project).filter(Project.storage_path == project_path).first()
        if isinstance(project, Project):
            return project
    except Exception:
        return _build_project_stub(folder_name, project_path)

    if project is not None:
        return _build_project_stub(folder_name, project_path)

    try:
        project = Project(
            name=folder_name,
            storage_path=project_path,
            original_path=project_name,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        return project
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return _build_project_stub(folder_name, project_path)


def _build_analysis_summary(
    project: Project,
    project_type: str,
    total_files: int,
    total_lines: int,
    languages: Counter,
    total_functions: int,
    total_classes: int,
    processed_files: list[dict],
    generated_test_cases: list[str],
    modules: list[dict],
    current_user: CurrentUser | None = None,
) -> dict:
    summary = {
        "project_name": project.name,
        "project_type": project_type,
        "total_files": total_files,
        "total_lines": total_lines,
        "language_count": len(languages),
        "function_count": total_functions,
        "class_count": total_classes,
        "languages": dict(languages),
        "files": processed_files,
        "processed_files": processed_files,
        "generated_test_cases": generated_test_cases,
        "modules": modules,
    }

    if current_user is not None:
        summary["generated_by_role"] = current_user.role
        summary["generated_by_username"] = current_user.username

    return summary


def _ensure_generated_test_case_table(db: Session) -> None:
    inspector = inspect(db.bind)
    if not inspector.has_table("generated_test_cases"):
        db.execute(text(
            "CREATE TABLE generated_test_cases ("
            "id UUID PRIMARY KEY, "
            "analysis_id UUID NOT NULL, "
            "project_id UUID NOT NULL, "
            "file_path VARCHAR(1000) NOT NULL, "
            "file_name VARCHAR(255) NOT NULL, "
            "language VARCHAR(100) NOT NULL, "
            "test_case TEXT NOT NULL, "
            "created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL"
            ");"
        ))
        db.commit()


def _save_analysis_result(
    db: Session,
    project: Project,
    total_files: int,
    total_lines: int,
    languages: Counter,
    total_functions: int,
    total_classes: int,
    summary: dict,
    generated_test_cases: list[dict] | None = None,
) -> str:
    analysis_id = str(uuid.uuid4())

    try:
        _ensure_generated_test_case_table(db)

        analysis_result = AnalysisResult(
            project_id=project.id,
            total_files=total_files,
            total_lines=total_lines,
            language_count=len(languages),
            function_count=total_functions,
            class_count=total_classes,
            summary=summary,
        )

        db.add(analysis_result)
        db.commit()
        db.refresh(analysis_result)
        analysis_id = str(analysis_result.id)

        if generated_test_cases:
            for file_entry in generated_test_cases:
                for test_case in file_entry.get("test_cases", []):
                    generated_entry = GeneratedTestCase(
                        analysis_id=analysis_result.id,
                        project_id=project.id,
                        file_path=file_entry.get("path", ""),
                        file_name=file_entry.get("name", ""),
                        language=file_entry.get("language", "Unknown"),
                        test_case=test_case,
                    )
                    db.add(generated_entry)
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    return analysis_id


@router.post("/analyze")
async def analyze_code(
    project_id: str | None = Form(None),
    project_name: str | None = Form(None),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """
    Analyze all source files from a selected project folder and generate
    test cases for each supported file.
    """

    try:
        project = _get_or_create_project(db, project_id, project_name)

        processed_files = []
        total_files = 0
        total_lines = 0
        total_functions = 0
        total_classes = 0
        languages = Counter()

        for upload_file in files:
            if not upload_file.filename:
                continue

            raw_content = await upload_file.read()

            try:
                content = raw_content.decode("utf-8", errors="ignore")
            except Exception:
                continue

            result = analyze_single_file(
                file_path=upload_file.filename,
                content=content,
            )

            processed_entry = {
                **result,
                "content": content,
                "module": module_key_for_path(result["path"]),
            }
            processed_files.append(processed_entry)

            total_files += 1
            total_lines += result["lines"]
            total_functions += result["functions"]
            total_classes += result["classes"]
            languages[result["language"]] += 1

        modules_summary = _generate_test_cases_by_module(processed_files)
        generated_test_cases = [
            test_case for file_info in processed_files for test_case in file_info["test_cases"]
        ]
        for file_info in processed_files:
            file_info.pop("content", None)

        project_type = classify_project_type(processed_files)

        summary = {
            "project_name": project.name,
            "project_type": project_type,
            "total_files": total_files,
            "total_lines": total_lines,
            "language_count": len(languages),
            "function_count": total_functions,
            "class_count": total_classes,
            "languages": dict(languages),
            "files": processed_files,
            "processed_files": processed_files,
            "generated_test_cases": generated_test_cases,
            "modules": modules_summary,
        }

        analysis_id = str(uuid.uuid4())

        try:
            analysis_result = AnalysisResult(
                project_id=project.id,
                total_files=total_files,
                total_lines=total_lines,
                language_count=len(languages),
                function_count=total_functions,
                class_count=total_classes,
                summary=summary,
            )

            db.add(analysis_result)
            db.commit()
            db.refresh(analysis_result)
            analysis_id = str(analysis_result.id)
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

        return {
            "success": True,
            "project_id": str(project.id),
            "project_name": project.name,
            "project_type": project_type,
            "analysis_id": analysis_id,
            "total_files": total_files,
            "total_lines": total_lines,
            "language_count": len(languages),
            "function_count": total_functions,
            "class_count": total_classes,
            "languages": dict(languages),
            "files": processed_files,
            "generated_test_cases": generated_test_cases,
            "modules": modules_summary,
            "summary": summary,
        }
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/save")
async def save_analysis_with_user(
    project_id: str | None = Form(None),
    project_name: str | None = Form(None),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user_optional),
):
    """
    Analyze source files, generate test cases, and save the result with the current user's role.
    If the request is unauthenticated, records the role as anonymous.
    """

    try:
        project = _get_or_create_project(db, project_id, project_name)

        processed_files = []
        total_files = 0
        total_lines = 0
        total_functions = 0
        total_classes = 0
        languages = Counter()

        for upload_file in files:
            if not upload_file.filename:
                continue

            raw_content = await upload_file.read()

            try:
                content = raw_content.decode("utf-8", errors="ignore")
            except Exception:
                continue

            result = analyze_single_file(
                file_path=upload_file.filename,
                content=content,
            )

            processed_entry = {
                **result,
                "content": content,
                "module": module_key_for_path(result["path"]),
            }
            processed_files.append(processed_entry)

            total_files += 1
            total_lines += result["lines"]
            total_functions += result["functions"]
            total_classes += result["classes"]
            languages[result["language"]] += 1

        modules_summary = _generate_test_cases_by_module(processed_files)
        generated_test_cases = [
            test_case for file_info in processed_files for test_case in file_info["test_cases"]
        ]
        for file_info in processed_files:
            file_info.pop("content", None)

        project_type = classify_project_type(processed_files)

        summary = _build_analysis_summary(
            project=project,
            project_type=project_type,
            total_files=total_files,
            total_lines=total_lines,
            languages=languages,
            total_functions=total_functions,
            total_classes=total_classes,
            processed_files=processed_files,
            generated_test_cases=generated_test_cases,
            modules=modules_summary,
            current_user=current_user,
        )

        analysis_id = _save_analysis_result(
            db=db,
            project=project,
            total_files=total_files,
            total_lines=total_lines,
            languages=languages,
            total_functions=total_functions,
            total_classes=total_classes,
            summary=summary,
            generated_test_cases=processed_files,
        )

        return {
            "success": True,
            "project_id": str(project.id),
            "project_name": project.name,
            "project_type": project_type,
            "analysis_id": analysis_id,
            "total_files": total_files,
            "total_lines": total_lines,
            "language_count": len(languages),
            "function_count": total_functions,
            "class_count": total_classes,
            "languages": dict(languages),
            "files": processed_files,
            "generated_test_cases": generated_test_cases,
            "modules": modules_summary,
            "summary": summary,
        }
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history")
def get_history(db: Session = Depends(get_db)):
    try:
        analyses = (
            db.query(AnalysisResult)
            .order_by(AnalysisResult.created_at.desc())
            .all()
        )
    except Exception:
        return {"success": True, "history": []}

    history = []
    for analysis in analyses:
        summary = analysis.summary or {}
        history.append(
            {
                "analysis_id": str(analysis.id),
                "project_name": summary.get("project_name") or "Imported Project",
                "project_type": summary.get("project_type") or "generic",
                "created_at": analysis.created_at.isoformat(),
                "total_files": summary.get("total_files", analysis.total_files),
                "generated_test_cases": summary.get("generated_test_cases", []),
                "processed_files": summary.get("processed_files", []),
            }
        )

    return {"success": True, "history": history}


@router.get("/download/{analysis_id}")
def download_analysis(analysis_id: str, format: str = "json", db: Session = Depends(get_db)):
    try:
        parsed_id = uuid.UUID(analysis_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid analysis id") from exc

    analysis = db.get(AnalysisResult, parsed_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    summary = analysis.summary or {}

    if format.lower() == "excel":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Analysis"
        sheet.append(["File", "Path", "Language", "Lines", "Functions", "Classes", "Test Cases"])

        for file_info in summary.get("processed_files", []):
            sheet.append(
                [
                    file_info.get("name", ""),
                    file_info.get("path", ""),
                    file_info.get("language", ""),
                    file_info.get("lines", 0),
                    file_info.get("functions", 0),
                    file_info.get("classes", 0),
                    " | ".join(file_info.get("test_cases", [])),
                ]
            )

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=analysis-{analysis_id}.xlsx"},
        )

    payload = json.dumps(summary, indent=2)
    return StreamingResponse(
        iter([payload.encode("utf-8")]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=analysis-{analysis_id}.json"},
    )