# Project Management API with AWS S3 & Event-Driven Architecture

This is a robust, containerized REST API built with **FastAPI** and **PostgreSQL**. It features Role-Based Access Control (RBAC), direct-to-S3 file uploads via Presigned URLs, and a serverless event-driven architecture using **AWS Lambda** for automatic image processing.

## Features
- **JWT Authentication**: Secure user registration and login.
- **RBAC**: Project ownership and participant roles (Owners can delete, Participants are restricted).
- **Direct-to-Cloud Storage**: Secure file uploads directly to AWS S3 bypassing the backend.
- **Event-Driven Image Processing**: AWS Lambda automatically resizes uploaded images (using `Pillow`) to save storage space.
- **Email Invite Simulation**: JWT-based secure invite links for adding participants to projects.
- **Dockerized**: Fully containerized backend and database for instant cross-platform setup.

## Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
- An AWS Account (AWS Academy / Learner Lab is supported).
- [uv](https://docs.astral.sh/uv/) (Extremely fast Python package and project manager).

## Local Setup (Windows & Linux)

### 1. Configure Environment Variables
Copy the provided example environment file and fill in your AWS credentials and S3 bucket name.
* **Windows (PowerShell):** `Copy-Item .env.example .env`
* **Linux/Mac:** `cp .env.example .env`

### 2. Run with Docker Compose
The following command will build the API image, pull PostgreSQL, execute the initial `init.sql` database migration, and link the services together.

```bash
docker compose up --build
```
*(To run it in the background, append `-d` to the command).*

### 3. Access the API
* Swagger UI Documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## Run from GitHub Container Registry (GHCR)

If you don't want to clone the repository or build the image locally, you can pull the ready-to-use production image directly from GitHub:

**1. Pull the image:**
```bash
docker pull ghcr.io/samekmat/projman:latest
```

**2. Run the container:**
You will need to provide your own environment variables (e.g., via a `.env` file or directly in the command):

```bash
docker run -p 8000:8000 --env-file .env ghcr.io/samekmat/projman:latest
```
*(Note: Ensure you have a PostgreSQL database running and accessible by the container via `DATABASE_URL`).*

---

## How to Upload Files (Direct-to-S3 Workflow)

Because this API uses a Serverless Event-Driven Architecture, files are not sent through the backend. Instead, you upload them directly to AWS S3 using a Presigned URL.

**Step 1: Generate an Upload URL**
Send a `POST` request to `/projects/{id}/documents` with the file metadata:
```json
{
  "filename": "cat.jpg",
  "content_type": "image/jpeg"
}
```
*The API will return a JSON containing the `upload_url`.*

**Step 2: Upload the File via cURL**
Use the generated URL to upload your physical file directly to the S3 bucket. Ensure the `Content-Type` header matches exactly what you provided in Step 1!

```bash
# Example for Windows/Linux:
curl -X PUT -T "./cat.jpg" -H "Content-Type: image/jpeg" "YOUR_LONG_PRESIGNED_UPLOAD_URL"
```
*If successful, AWS Lambda will automatically intercept this file, resize it (if it's an image), and save it with a `processed-` prefix!*

---

## Testing

The project includes three types of tests: automated logic verification using **Pytest**, manual/semi-automated API testing using a **`.http`** file, and load testing using **Locust**.

### 1. Automated Tests (Pytest)
Automated tests are used to verify the application's logic in isolation (using database mocking).

**Prerequisites:** Ensure your dependencies (including dev packages) are installed using `uv`:
```bash
uv sync
```

**Running tests:**
```bash
uv run pytest
```
*Tests are configured in `pytest.ini` and use `tests/test_api.py`.*

### 2. Manual API Client (`test_main.http`)
The `test_main.http` file allows you to execute real HTTP requests directly from your IDE (PyCharm or VS Code with REST Client extension).

**How to use:**
1. Start the application (`docker compose up` or `uv run uvicorn src.main:app`).
2. Open `test_main.http` in your IDE.
3. Click the **green "Play" icon** next to a request to execute it.
4. **Authentication Flow:**
    - Execute the **"Register new user"** request.
    - Execute the **"Login (get token)"** request. The script will automatically save the token to a global variable `{{auth_token}}`.
    - Subsequent requests (Projects, Documents) will automatically use this token.
5. **Resource Management:** The file is structured to first create resources (Project -> Document) and then clean them up at the end.

### 3. Load Testing (Locust)
Locust is used to simulate concurrent users and measure the performance of the API.

**Running Locust:**
1. Start the application and its database (`docker compose up`).
2. Run Locust from the terminal using `uv`:
   ```bash
   uv run locust
   ```
3. Open your browser at [http://localhost:8089](http://localhost:8089).
4. Enter the target host (e.g., `http://localhost:8000`), number of users, and spawn rate.
5. Start swarming.

The `locustfile.py` is configured to:
- Automatically register and log in unique users.
- Perform random operations: checking profile, listing/creating projects, and initializing document uploads.

---

## AWS Cloud Setup Guide

To fully utilize the cloud features (S3 Uploads and Lambda Image Processing), follow these step-by-step instructions in your AWS Management Console.

### 1. S3 Bucket Configuration
1. Go to **S3** and click **Create bucket**.
2. Name it uniquely (e.g., `pm-app-yourname-123`) and select your region.
3. Keep **Block all public access** enabled.
4. Click **Create bucket**.

### 2. AWS Lambda Execution Role
1. Go to **IAM** -> **Roles** -> **Create role**.
2. Select **AWS service** -> **Lambda**, then click Next.
3. Search for and attach the **AmazonS3FullAccess** policy.
4. Name the role `LambdaS3ProcessorRole` and click **Create role**.

### 3. AWS Lambda Function (Image Resizer)
1. Go to **Lambda** -> **Create function** -> *Author from scratch*.
2. Name it `ProcessProjectFiles`.
3. Set **Runtime** strictly to **Python 3.12**.
4. Expand *Change default execution role*, select *Use an existing role*, and pick the `LambdaS3ProcessorRole`.
5. Click **Create function**.
6. Under the **Code** tab, paste the contents of `aws_lambda/lambda_function.py` and click **Deploy**.

### 4. Adding the Pillow Layer (For Image Processing)
1. Scroll down to the **Layers** section of your Lambda function.
2. Click **Add a layer** -> **Specify an ARN**.
3. Paste the ARN for your region (e.g., for `us-east-1`):
   `arn:aws:lambda:us-east-1:770693421928:layer:Klayers-p312-Pillow:10`
4. Click **Verify** and **Add**.

### 5. Lambda Configuration Tuning
1. Go to the **Configuration** tab -> **General configuration** -> **Edit**.
2. Increase **Memory** to `512 MB`.
3. Increase **Timeout** to `30 seconds`.
4. Click **Save**.

### 6. Linking S3 to Lambda (The Trigger)
1. On your Lambda function overview, click **Add trigger**.
2. Select **S3** from the dropdown.
3. Choose your newly created bucket.
4. Leave Event types as *All object create events*.
5. Acknowledge the recursive invocation warning and click **Add**.