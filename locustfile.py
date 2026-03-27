import uuid

from locust import HttpUser, between, task


class FastAPIUser(HttpUser):
    wait_time = between(1, 3)
    token = None
    project_id = None
    document_id = None

    def on_start(self):
        """Method called when a Locust user starts. Performs registration and login."""
        self.username = f"locust_user_{uuid.uuid4().hex[:8]}"
        self.password = "secret_password_123"

        self.client.post(
            "/auth",
            json={
                "login": self.username,
                "password": self.password,
                "repeat_password": self.password,
            },
        )

        response = self.client.post(
            "/login", data={"username": self.username, "password": self.password}
        )

        if response.status_code == 200:
            self.token = response.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(1)
    def check_health(self):
        """Check application health status."""
        self.client.get("/health")

    @task(2)
    def check_me(self):
        """Check user profile."""
        if self.token:
            self.client.get("/me", headers=self.headers)

    @task(5)
    def project_operations(self):
        """Scenario for operations on projects."""
        if not self.token:
            return

        self.client.get("/projects", headers=self.headers)

        create_resp = self.client.post(
            "/projects",
            headers=self.headers,
            json={
                "name": f"Locust Project {uuid.uuid4().hex[:4]}",
                "description": "Load test project",
            },
        )

        if create_resp.status_code == 201:
            pid = create_resp.json().get("project_id")
            self.client.get(f"/projects/{pid}", headers=self.headers)

    @task(3)
    def document_operations(self):
        """Scenario for operations on documents (requires a project)."""
        if not self.token:
            return

        proj_resp = self.client.get("/projects", headers=self.headers)
        if proj_resp.status_code == 200 and proj_resp.json():
            pid = proj_resp.json()[0]["id"]

            doc_resp = self.client.post(
                f"/{pid}/documents",
                headers=self.headers,
                json={"filename": "load_test.pdf", "content_type": "application/pdf"},
            )

            if doc_resp.status_code == 201:
                did = doc_resp.json().get("document_id")
                self.client.get(f"/document/{did}", headers=self.headers)
