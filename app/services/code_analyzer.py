from pathlib import Path
import re


SUPPORTED_EXTENSIONS = {
    ".py": "Python",
    ".java": "Java",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript React",
    ".jsx": "JavaScript React",
    ".cs": "C#",
    ".go": "Go",
    ".php": "PHP",
    ".rb": "Ruby",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++ Header",
    ".html": "HTML",
    ".css": "CSS",
    ".sql": "SQL",
}


def count_lines(content: str) -> int:
    return len(content.splitlines())


def analyze_python(content: str) -> tuple[int, int]:
    functions = len(
        re.findall(
            r"^\s*(?:async\s+)?def\s+\w+",
            content,
            re.MULTILINE,
        )
    )

    classes = len(
        re.findall(
            r"^\s*class\s+\w+",
            content,
            re.MULTILINE,
        )
    )

    return functions, classes


def analyze_java(content: str) -> tuple[int, int]:
    methods = len(
        re.findall(
            r"(?:public|private|protected)?\s+"
            r"(?:static\s+)?[\w<>\[\]]+\s+\w+\s*\([^)]*\)\s*\{",
            content,
        )
    )

    classes = len(
        re.findall(
            r"\bclass\s+\w+",
            content,
        )
    )

    return methods, classes


def analyze_javascript(content: str) -> tuple[int, int]:
    functions = len(
        re.findall(
            r"\bfunction\s+\w+\s*\(",
            content,
        )
    )

    functions += len(
        re.findall(
            r"\b(?:const|let|var)\s+\w+\s*=\s*\([^)]*\)\s*=>",
            content,
        )
    )

    classes = len(
        re.findall(
            r"\bclass\s+\w+",
            content,
        )
    )

    return functions, classes


def analyze_project(project_path: str) -> dict:

    root = Path(project_path)

    total_files = 0
    total_lines = 0
    total_functions = 0
    total_classes = 0

    languages = {}

    files = []

    for file_path in root.rglob("*"):

        if not file_path.is_file():
            continue

        extension = file_path.suffix.lower()

        if extension not in SUPPORTED_EXTENSIONS:
            continue

        language = SUPPORTED_EXTENSIONS[extension]

        try:
            content = file_path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        except Exception:
            continue

        lines = count_lines(content)

        functions = 0
        classes = 0

        if language == "Python":
            functions, classes = analyze_python(
                content
            )

        elif language == "Java":
            functions, classes = analyze_java(
                content
            )

        elif language in (
            "JavaScript",
            "TypeScript",
            "JavaScript React",
            "TypeScript React",
        ):
            functions, classes = analyze_javascript(
                content
            )

        total_files += 1
        total_lines += lines
        total_functions += functions
        total_classes += classes

        languages[language] = (
            languages.get(language, 0) + 1
        )

        files.append(
            {
                "name": file_path.name,
                "path": str(
                    file_path.relative_to(root)
                ),
                "language": language,
                "lines": lines,
                "functions": functions,
                "classes": classes,
            }
        )

    return {
        "total_files": total_files,
        "total_lines": total_lines,
        "language_count": len(languages),
        "function_count": total_functions,
        "class_count": total_classes,
        "languages": languages,
        "files": files,
    }
