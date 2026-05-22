import unittest
import requests

BASE_URL = "http://127.0.0.1:5000"

class TestMovieAPIUltimate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        res_admin = requests.post(f"{BASE_URL}/users/login", json={"username": "admin", "password": "admin"})
        cls.admin_token = res_admin.json().get("access_token")
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}
        
        res_user = requests.post(f"{BASE_URL}/users/login", json={"username": "user", "password": "user"})
        cls.user_token = res_user.json().get("access_token")
        cls.user_headers = {"Authorization": f"Bearer {cls.user_token}"}
        
        cls.test_collection_id = None

    def test_01_login_invalid_credentials(self):
        """
        Requirement: 1
        Purpose: Edge case test. Verify that the system correctly intercepts incorrect passwords and returns a 401 status code with a clear error message.
        """
        res = requests.post(f"{BASE_URL}/users/login", json={"username": "admin", "password": "wrong"})
        
        self.assertEqual(res.status_code, 401)
        self.assertIn("Wrong username", res.json().get("message", ""))

    def test_02_user_management_access(self):
        """
        Requirement: 1
        Purpose: Edge case test. Verify that an unauthorized User attempting to access the Admin-only user list is blocked with a 403 status code.
        """
        res = requests.get(f"{BASE_URL}/users/", headers=self.user_headers)
        
        self.assertEqual(res.status_code, 403)
        self.assertIn("Admin only", res.json().get("message", ""))

    def test_03_import_wrong_file_type(self):
        """
        Requirement: 2
        Purpose: Edge case test. Verify that uploading a non-CSV file (invalid format) returns a 400 status code with an appropriate error message.
        """
        files = {
            'movies_file': ('movies.txt', 'dummy data'),
            'credits_file': ('credits.csv', 'dummy data')
        }
        res = requests.post(f"{BASE_URL}/movies/import", headers=self.admin_headers, files=files)
        
        self.assertEqual(res.status_code, 400)
        self.assertIn("Wrong file type", res.json().get("message", ""))

    def test_04_import_success_mock_data(self):
        """
        Requirement: 2
        Purpose: Main functionality test. Verify that the Admin can successfully import valid CSV data and receive a 201 status code.
        """
        mock_movies = 'id,title,release_date,overview,genres\n999999,Test Movie,2026-01-01,Test Overview,"[{""name"": ""Action""}]"'
        mock_credits = 'movie_id,title,cast,crew\n999999,Test Movie,"[{""id"": 888, ""name"": ""Test Actor"", ""character"": ""Hero""}]","[{""id"": 777, ""name"": ""Test Director"", ""job"": ""Director"", ""department"": ""Directing""}]"'
        
        files = {
            'movies_file': ('movies.csv', mock_movies),
            'credits_file': ('credits.csv', mock_credits)
        }
        res = requests.post(f"{BASE_URL}/movies/import", headers=self.admin_headers, files=files)
            
        self.assertEqual(res.status_code, 201)

    def test_05_get_movie_structure_and_data(self):
        """
        Requirement: 3
        Purpose: Main functionality test. Verify that querying movie details returns a complete JSON response structure and correct data.
        """
        res = requests.get(f"{BASE_URL}/movies/999999", headers=self.user_headers)
        
        self.assertEqual(res.status_code, 200)
        
        data = res.json()
        
        self.assertIsInstance(data, dict)
        self.assertIn("id", data)
        self.assertIn("title", data)
        self.assertIn("release_date", data)
        self.assertIn("overview", data)
        self.assertIn("genres", data)
        
        self.assertEqual(data["title"], "Test Movie")
        self.assertEqual(data["id"], 999999)

    def test_06_search_movies_fuzz(self):
        """
        Requirement: 3
        Purpose: Main functionality test. Verify that the fuzzy search endpoint returns the correct JSON array structure.
        """
        res = requests.get(f"{BASE_URL}/movies/search?q=Test Movie", headers=self.user_headers)
        
        self.assertEqual(res.status_code, 200)
        
        data = res.json()
        self.assertIsInstance(data, list)
        if len(data) > 0:
            self.assertIsInstance(data[0], dict)
            self.assertIn("title", data[0])

    def test_07_playlist_crud_flow_and_structure(self):
        """
        Requirement: 4
        Purpose: Main functionality test. Verify the JSON structure when creating a playlist, adding a movie to it, and retrieving the playlist.
        """
        res_create = requests.post(f"{BASE_URL}/collections/", headers=self.user_headers, json={"name": "My Test List"})
        self.assertEqual(res_create.status_code, 201)
        
        c_id = res_create.json().get("id")
        TestMovieAPIUltimate.test_collection_id = c_id
        
        res_add = requests.post(f"{BASE_URL}/collections/{c_id}/movies/999999", headers=self.user_headers)
        self.assertEqual(res_add.status_code, 201)
        
        res_get = requests.get(f"{BASE_URL}/collections/", headers=self.user_headers)
        self.assertEqual(res_get.status_code, 200)
        
        data = res_get.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        
        first_playlist = data[-1]
        self.assertIn("id", first_playlist)
        self.assertIn("name", first_playlist)
        self.assertIn("movies", first_playlist)
        self.assertIsInstance(first_playlist["movies"], list)

    def test_08_playlist_isolation(self):
        """
        Requirement: 4
        Purpose: Edge case test. Verify privacy isolation by ensuring an Admin attempting to add a movie to a regular User's playlist is blocked with a 403 status code.
        """
        c_id = TestMovieAPIUltimate.test_collection_id
        res = requests.post(f"{BASE_URL}/collections/{c_id}/movies/999999", headers=self.admin_headers)
        
        self.assertEqual(res.status_code, 403)
        self.assertIn("Forbidden", res.json().get("message", ""))

    def test_09_statistics_invalid_format(self):
        """
        Requirement: 5
        Purpose: Edge case test. Verify that requesting an unsupported data format (e.g., pdf) for statistics returns a 400 status code.
        """
        res = requests.get(f"{BASE_URL}/statistics/?format=pdf", headers=self.admin_headers)
        
        self.assertEqual(res.status_code, 400)
        self.assertIn("csv' or 'png", res.json().get("message", ""))

    def test_10_statistics_data_formats(self):
        """
        Requirement: 5
        Purpose: Main functionality test. Verify that the endpoint correctly returns CSV or PNG data streams based on the requested format parameter.
        """
        res_csv = requests.get(f"{BASE_URL}/statistics/?format=csv", headers=self.user_headers)
        
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn("text/csv", res_csv.headers.get('Content-Type'))
        
        res_png = requests.get(f"{BASE_URL}/statistics/?format=png", headers=self.user_headers)
        
        self.assertEqual(res_png.status_code, 200)
        self.assertEqual(res_png.headers.get('Content-Type'), 'image/png')

if __name__ == '__main__':
    unittest.main(verbosity=2, failfast=False)