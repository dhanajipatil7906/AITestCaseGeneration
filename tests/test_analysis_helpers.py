import unittest
from unittest.mock import Mock

from app.api import analysis as analysis_module
from app.api.analysis import classify_project_type, generate_test_cases_for_file


class AnalysisHelpersTest(unittest.TestCase):
    def test_classify_project_type_detects_dotnet_controller_files(self):
        files = [
            {"path": "src/Controllers/UsersController.cs", "language": "C#"},
            {"path": "src/Models/User.cs", "language": "C#"},
        ]

        project_type = classify_project_type(files)

        self.assertEqual(project_type, "dotnet")

    def test_generate_test_cases_for_file_creates_cases_for_controller(self):
        file_info = {
            "path": "src/Controllers/UsersController.cs",
            "language": "C#",
            "content": "public class UsersController { public IActionResult GetUsers() { return Ok(); } }",
        }

        test_cases = generate_test_cases_for_file(file_info)

        self.assertEqual(len(test_cases), 5)
        self.assertTrue(any("UsersController" in case for case in test_cases))
        self.assertTrue(any("GetUsers" in case for case in test_cases))
        self.assertTrue(any("invalid" in case.lower() or "error" in case.lower() for case in test_cases))
        self.assertTrue(any("maximum valid" in case.lower() or "maximum input" in case.lower() for case in test_cases))

    def test_get_or_create_project_falls_back_when_database_query_fails(self):
        db = Mock()
        db.get.side_effect = Exception("database schema mismatch")

        project = analysis_module._get_or_create_project(db, None, "Fallback Project")

        self.assertEqual(project.name, "Fallback Project")
        self.assertTrue(project.id)


if __name__ == "__main__":
    unittest.main()
