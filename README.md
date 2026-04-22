# Atlas — Watch Flip Tracker

Atlas is a serverless Python web application for tracking watch flipping projects. It lets a single user manage a portfolio of watches through their full lifecycle: acquisition, expense tracking, sale, and profit/loss analysis.

## Architecture

```
Browser ──HTTPS──▶ CloudFront ──▶ S3 (static frontend)
Browser ──API────▶ API Gateway ──▶ Lambda (Python 3.12) ──▶ DynamoDB / S3 / Secrets Manager
```

All infrastructure is defined in a single AWS SAM template (`template.yaml`) and deployed with one command.

| Component | AWS Service |
|---|---|
| Frontend hosting | S3 + CloudFront (HTTPS) |
| API | API Gateway HTTP API |
| Compute | Lambda (Python 3.12) |
| Database | DynamoDB (single-table design) |
| Image storage | S3 (pre-signed URL uploads) |
| Secrets | Secrets Manager |

## Project Structure

```
atlas/
├── src/
│   ├── handler.py                  # Lambda entry point and route dispatcher
│   ├── utils.py                    # Response helpers, request parsing
│   └── services/
│       ├── auth_service.py         # Login, JWT, lockout
│       ├── watch_service.py        # Watch CRUD, filtering, sorting
│       ├── expense_service.py      # Expense CRUD
│       ├── sale_service.py         # Sale CRUD, status transitions
│       ├── image_service.py        # Image upload (pre-signed URLs)
│       └── profit_loss_service.py  # P&L calculation
├── frontend/
│   ├── index.html                  # Single-page app entry point
│   ├── css/styles.css              # Responsive styles
│   └── js/                         # Vanilla JS SPA modules
│       ├── utils.js                # Currency/date formatting helpers
│       ├── api.js                  # Fetch wrapper with JWT
│       ├── auth.js                 # Login page logic
│       ├── app.js                  # SPA router
│       ├── dashboard.js            # Watch list with accordion cards
│       ├── watch-form.js           # Add/edit watch form
│       ├── portfolio.js            # Portfolio summary + filters
│       └── image-upload.js         # Drag-and-drop image upload
├── tests/
│   ├── conftest.py                 # Shared fixtures and Hypothesis strategies
│   ├── unit/                       # Unit tests (170 tests)
│   ├── property/                   # Property-based tests (52 tests)
│   └── integration/                # End-to-end Lambda handler tests (26 tests)
├── scripts/
│   └── setup-secrets.sh            # Secrets Manager provisioning
├── template.yaml                   # AWS SAM infrastructure template
├── requirements.txt                # Runtime dependencies
└── requirements-dev.txt            # Dev/test dependencies
```

---

## Running Locally

This section covers how to run Atlas on your machine for development and testing. No AWS account is needed for local development — all AWS services are mocked in tests, and SAM CLI can emulate the API locally.

### Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.12+ | `brew install python@3.12` or [python.org](https://www.python.org/downloads/) |
| AWS SAM CLI | Latest | `brew install aws-sam-cli` or [install guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) |
| Docker | Latest | Required by `sam local`. [Get Docker](https://docs.docker.com/get-docker/) |
| AWS CLI v2 | Latest | `brew install awscli` (only needed for deployment, not local dev) |

### 1. Set up the Python environment

```bash
# Clone the repo
git clone <repo-url>
cd atlas

# Create and activate a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install all dependencies
pip install -r requirements.txt -r requirements-dev.txt
```

### 2. Run the test suite

All tests use moto to mock AWS services — no real AWS credentials needed.

```bash
# Run everything (248 tests)
pytest

# Run with verbose output
pytest -v

# Run specific test categories
pytest tests/unit/ -v              # 170 unit tests
pytest tests/property/ -v          # 52 property-based tests (Hypothesis)
pytest tests/integration/ -v       # 26 end-to-end tests

# Run with coverage report
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

### 3. Run the API locally with SAM CLI

SAM CLI can emulate the API Gateway + Lambda locally using Docker. This gives you a real HTTP server you can hit with curl or the frontend.

```bash
# Build the SAM application
sam build

# Start the local API (runs on http://127.0.0.1:3000)
sam local start-api
```

The local API needs real AWS credentials to access DynamoDB, S3, and Secrets Manager in your AWS account. If you want to test against real AWS services:

```bash
# Make sure your AWS CLI is configured
aws configure

# Provision the secret (one-time setup)
chmod +x scripts/setup-secrets.sh
./scripts/setup-secrets.sh

# Deploy just the DynamoDB table and S3 buckets first (or use the full deploy)
sam build && sam deploy --guided

# Then start the local API (it uses the deployed DynamoDB/S3/Secrets Manager)
sam local start-api --env-vars env.json
```

Create an `env.json` file to point the local Lambda at your deployed resources:

```json
{
  "AtlasFunction": {
    "TABLE_NAME": "atlas-table-prod",
    "IMAGE_BUCKET_NAME": "atlas-images-<account-id>-prod",
    "SECRET_NAME": "atlas-secret-prod"
  }
}
```

Replace the values with the actual resource names from your deployment (see `sam deploy` outputs or check CloudFormation).

### 4. Serve the frontend locally

The frontend is plain HTML/CSS/JS with no build step. Serve it with any static file server:

```bash
# Option A: Python's built-in server
python -m http.server 8080 --directory frontend

# Option B: npx (if you have Node.js)
npx serve frontend -l 8080
```

Then open http://localhost:8080 in your browser.

To connect the frontend to the local SAM API, add this line to `frontend/index.html` before the other `<script>` tags:

```html
<script>window.ATLAS_API_URL = "http://127.0.0.1:3000";</script>
```

Or set it in the browser console:

```javascript
window.ATLAS_API_URL = "http://127.0.0.1:3000";
```

### 5. Local development workflow

A typical development loop looks like:

1. Edit source code in `src/`
2. Run relevant tests: `pytest tests/unit/test_watch_service.py -v`
3. If testing the full API: `sam build && sam local start-api`
4. If testing the frontend: serve `frontend/` and point it at the local API
5. Run the full suite before committing: `pytest`

---

## Production Deployment

This section is a complete, step-by-step guide to deploying Atlas to a fresh AWS account. By the end, you'll have a live application accessible via HTTPS.

### Prerequisites

| Requirement | Details |
|---|---|
| AWS account | With admin or sufficient IAM permissions |
| AWS CLI v2 | Installed and configured with credentials |
| AWS SAM CLI | Installed ([guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)) |
| Python 3.12 | For the setup script (bcrypt hashing) |
| Docker | Required by `sam build` for Lambda packaging |

Verify your tools are ready:

```bash
aws --version          # aws-cli/2.x.x
sam --version          # SAM CLI, version 1.x.x
python3 --version      # Python 3.12.x
docker --version       # Docker version 2x.x.x
```

### Step 1: Configure AWS credentials

```bash
aws configure
```

Enter your Access Key ID, Secret Access Key, default region (e.g. `us-east-1`), and output format (`json`). The region you choose here is where all Atlas resources will be created.

To verify:

```bash
aws sts get-caller-identity
```

You should see your account ID and IAM user/role ARN.

### Step 2: Clone and install dependencies

```bash
git clone <repo-url>
cd atlas

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

### Step 3: Run tests to verify everything works

```bash
pytest
```

All 248 tests should pass. This confirms the code is correct before deploying.

### Step 4: Provision the authentication secret

The setup script creates a Secrets Manager secret with your login credentials:

```bash
chmod +x scripts/setup-secrets.sh
./scripts/setup-secrets.sh
```

You'll be prompted for:

| Prompt | Default | What it does |
|---|---|---|
| Username | `admin` | Your login username |
| Password | (none) | Your login password — bcrypt-hashed with cost factor 12 |
| AWS region | `us-east-1` | Must match your deployment region |
| Stage name | `prod` | Must match the `StageName` parameter in SAM deploy |

The script generates a random 32-byte JWT signing key automatically.

**Important:** The region and stage name you enter here must match what you use in `sam deploy`. If you deploy to `us-west-2` with stage `prod`, run the script with those same values.

### Step 5: Build the SAM application

```bash
sam build
```

This packages the Lambda function code and dependencies into `.aws-sam/build/`. It uses Docker to build in a Lambda-compatible environment.

If the build succeeds, you'll see:

```
Build Succeeded
```

### Step 6: Deploy to AWS

For the first deployment, use `--guided` to walk through the configuration:

```bash
sam deploy --guided
```

Answer the prompts:

| Prompt | Recommended value |
|---|---|
| Stack Name | `atlas` |
| AWS Region | Same region as your secret (e.g. `us-east-1`) |
| Parameter StageName | `prod` |
| Confirm changes before deploy | `y` |
| Allow SAM CLI IAM role creation | `y` |
| Disable rollback | `n` |
| Save arguments to configuration file | `y` |
| SAM configuration file | `samconfig.toml` |
| SAM configuration environment | `default` |

SAM will show you a changeset of all resources to be created. Type `y` to confirm.

This creates:
- 1 DynamoDB table
- 2 S3 buckets (images + web assets)
- 1 CloudFront distribution
- 1 Lambda function
- 1 HTTP API Gateway with 19 routes
- 1 Secrets Manager secret (placeholder — your real secret was created in Step 4)
- IAM roles with least-privilege permissions

Deployment takes 3-5 minutes. CloudFront distribution creation can take up to 15 minutes on the first deploy.

### Step 7: Note the stack outputs

After deployment, SAM prints the stack outputs. Save these — you'll need them:

```bash
# Or retrieve them anytime with:
aws cloudformation describe-stacks --stack-name atlas --query 'Stacks[0].Outputs' --output table
```

| Output | Example | Purpose |
|---|---|---|
| `ApiEndpoint` | `https://abc123.execute-api.us-east-1.amazonaws.com/prod` | API URL for the frontend |
| `WebDistributionUrl` | `https://d1234abcdef.cloudfront.net` | Your app's public URL |
| `WebDistributionId` | `E1234ABCDEF` | For cache invalidation |
| `WebAssetsBucketName` | `atlas-web-123456789012-prod` | Where frontend files go |
| `ImagesBucketName` | `atlas-images-123456789012-prod` | Where watch images are stored |
| `AtlasTableName` | `atlas-table-prod` | DynamoDB table name |
| `AtlasSecretArn` | `arn:aws:secretsmanager:...` | Secret ARN |

### Step 8: Configure and upload the frontend

First, inject the API URL into the frontend:

```bash
# Get the API endpoint
API_URL=$(aws cloudformation describe-stacks \
  --stack-name atlas \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text)

echo "API URL: $API_URL"
```

Create a config file that the frontend will load. Add this line to `frontend/index.html`, right before the `<script src="js/utils.js">` tag:

```html
<script>window.ATLAS_API_URL = "https://abc123.execute-api.us-east-1.amazonaws.com/prod";</script>
```

Replace the URL with your actual `ApiEndpoint` value.

Then upload the frontend to S3:

```bash
# Get the web assets bucket name
WEB_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name atlas \
  --query 'Stacks[0].Outputs[?OutputKey==`WebAssetsBucketName`].OutputValue' \
  --output text)

# Upload all frontend files
aws s3 sync frontend/ s3://$WEB_BUCKET/ --delete

# Invalidate CloudFront cache so changes appear immediately
DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name atlas \
  --query 'Stacks[0].Outputs[?OutputKey==`WebDistributionId`].OutputValue' \
  --output text)

aws cloudfront create-invalidation --distribution-id $DIST_ID --paths "/*"
```

### Step 9: Access your application

```bash
# Get the CloudFront URL
aws cloudformation describe-stacks \
  --stack-name atlas \
  --query 'Stacks[0].Outputs[?OutputKey==`WebDistributionUrl`].OutputValue' \
  --output text
```

Open the URL in your browser. Log in with the username and password you set in Step 4.

### Subsequent deployments

After the first deploy, updates are simpler:

```bash
# Code changes
sam build && sam deploy

# Frontend-only changes
WEB_BUCKET=$(aws cloudformation describe-stacks --stack-name atlas --query 'Stacks[0].Outputs[?OutputKey==`WebAssetsBucketName`].OutputValue' --output text)
aws s3 sync frontend/ s3://$WEB_BUCKET/ --delete

DIST_ID=$(aws cloudformation describe-stacks --stack-name atlas --query 'Stacks[0].Outputs[?OutputKey==`WebDistributionId`].OutputValue' --output text)
aws cloudfront create-invalidation --distribution-id $DIST_ID --paths "/*"
```

### Changing your password

Re-run the setup script. It detects the existing secret and updates it:

```bash
./scripts/setup-secrets.sh
```

The change takes effect immediately — no redeployment needed. The Lambda function picks up the new secret on its next cold start (or within a few minutes as the cached secret expires).

### Hosting under a subpath on an existing domain (`yourdomain.com/atlas`)

If you already have a domain with a Route 53 hosted zone and a CloudFront distribution serving other content, you can add Atlas as a subpath (`/atlas`) on that same domain. This avoids creating a separate domain or subdomain.

The approach: add the Atlas S3 bucket and API Gateway as additional origins on your **existing** CloudFront distribution, with path-based cache behaviors that route `/atlas/*` to Atlas and `/atlas/api/*` to the API.

#### Architecture

```
yourdomain.com/            → your existing origin (unchanged)
yourdomain.com/atlas/      → Atlas S3 bucket (frontend files)
yourdomain.com/atlas/api/  → Atlas API Gateway (Lambda backend)
```

#### Prerequisites

- An existing CloudFront distribution serving `yourdomain.com`
- An ACM certificate in `us-east-1` covering `yourdomain.com`
- A Route 53 hosted zone for `yourdomain.com` (already pointing at your CloudFront distribution)
- Atlas deployed via `sam deploy` (Steps 1-6 above completed)

#### Step A: Gather Atlas resource info

```bash
# Atlas S3 web bucket domain
WEB_BUCKET=$(aws cloudformation describe-stacks --stack-name atlas \
  --query 'Stacks[0].Outputs[?OutputKey==`WebAssetsBucketName`].OutputValue' --output text)

echo "S3 bucket: $WEB_BUCKET"
echo "S3 domain: $WEB_BUCKET.s3.amazonaws.com"

# Atlas API Gateway endpoint (strip the stage path for the origin domain)
API_URL=$(aws cloudformation describe-stacks --stack-name atlas \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' --output text)

echo "API URL: $API_URL"
# Extract just the domain: abc123.execute-api.us-east-1.amazonaws.com
API_DOMAIN=$(echo "$API_URL" | sed 's|https://||' | cut -d'/' -f1)
echo "API domain: $API_DOMAIN"

# The stage name (usually "prod")
API_STAGE=$(echo "$API_URL" | sed 's|https://||' | cut -d'/' -f2)
echo "API stage: $API_STAGE"
```

#### Step B: Upload frontend files under the `atlas/` prefix

Instead of uploading to the root of the S3 bucket, upload under an `atlas/` prefix:

```bash
aws s3 sync frontend/ s3://$WEB_BUCKET/atlas/ --delete
```

The files will be at paths like `atlas/index.html`, `atlas/css/styles.css`, `atlas/js/app.js`, etc.

#### Step C: Update `frontend/index.html` for subpath hosting

Add a `<base>` tag so relative asset paths resolve correctly, and set the API URL:

```html
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <base href="/atlas/">
  <title>Atlas — Watch Flip Tracker</title>
  <link rel="stylesheet" href="css/styles.css">
</head>
```

And before the script tags at the bottom:

```html
<script>window.ATLAS_API_URL = "https://yourdomain.com/atlas/api";</script>
```

Re-upload after editing:

```bash
aws s3 sync frontend/ s3://$WEB_BUCKET/atlas/ --delete
```

#### Step D: Add origins to your existing CloudFront distribution

Open your existing CloudFront distribution in the AWS Console (or use the CLI/IaC). Add two new origins:

**Origin 1 — Atlas S3 bucket (frontend)**

| Setting | Value |
|---|---|
| Origin Domain | `<WEB_BUCKET>.s3.<region>.amazonaws.com` |
| Origin ID | `AtlasS3Origin` |
| Origin Path | (leave empty) |
| Origin Access | Origin Access Control (OAC) or Origin Access Identity (OAI) — grant CloudFront read access to the bucket |
| Protocol | HTTPS Only |

If using OAC (recommended), create an Origin Access Control and update the S3 bucket policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCloudFrontOAC",
      "Effect": "Allow",
      "Principal": {
        "Service": "cloudfront.amazonaws.com"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::<WEB_BUCKET>/*",
      "Condition": {
        "StringEquals": {
          "AWS:SourceArn": "arn:aws:cloudfront::<ACCOUNT_ID>:distribution/<YOUR_EXISTING_DIST_ID>"
        }
      }
    }
  ]
}
```

**Origin 2 — Atlas API Gateway (backend)**

| Setting | Value |
|---|---|
| Origin Domain | `abc123.execute-api.us-east-1.amazonaws.com` |
| Origin ID | `AtlasAPIOrigin` |
| Origin Path | `/<stage>` (e.g. `/prod`) |
| Protocol | HTTPS Only |
| Origin SSL Protocols | TLSv1.2 |

Setting the Origin Path to `/<stage>` means CloudFront strips `/atlas/api` from the request and prepends `/<stage>`, so `/atlas/api/watches` becomes `/<stage>/watches` at the API Gateway.

#### Step E: Add cache behaviors to your existing CloudFront distribution

Add these behaviors **above** your existing default behavior (order matters — CloudFront evaluates top to bottom):

**Behavior 1 — API requests (`/atlas/api/*`)**

| Setting | Value |
|---|---|
| Path Pattern | `/atlas/api/*` |
| Origin | `AtlasAPIOrigin` |
| Viewer Protocol Policy | HTTPS Only |
| Allowed HTTP Methods | GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE |
| Cache Policy | `CachingDisabled` (managed policy) |
| Origin Request Policy | `AllViewerExceptHostHeader` (managed policy) |

This forwards all API requests to the Lambda backend with no caching.

**Behavior 2 — Frontend assets (`/atlas/*`)**

| Setting | Value |
|---|---|
| Path Pattern | `/atlas/*` |
| Origin | `AtlasS3Origin` |
| Viewer Protocol Policy | Redirect HTTP to HTTPS |
| Allowed HTTP Methods | GET, HEAD, OPTIONS |
| Cache Policy | `CachingOptimized` (managed policy) or custom with TTL |
| Compress | Yes |

**Behavior 3 — SPA fallback (`/atlas`)**

| Setting | Value |
|---|---|
| Path Pattern | `/atlas` |
| Origin | `AtlasS3Origin` |
| Viewer Protocol Policy | Redirect HTTP to HTTPS |
| Allowed HTTP Methods | GET, HEAD |
| Cache Policy | `CachingOptimized` |

Add a custom error response on the distribution (or a CloudFront Function) to serve `atlas/index.html` for 403/404 errors on the `/atlas/*` path. The simplest approach is a CloudFront Function:

```javascript
// CloudFront Function: atlas-spa-rewrite
// Associate with Behavior 2 (viewer request)
function handler(event) {
  var request = event.request;
  var uri = request.uri;

  // If the request is for /atlas or /atlas/ with no file extension, serve index.html
  if (uri === '/atlas' || uri === '/atlas/') {
    request.uri = '/atlas/index.html';
  }
  // If the URI starts with /atlas/ and has no file extension, it's a SPA route
  else if (uri.startsWith('/atlas/') && !uri.match(/\.\w+$/)) {
    request.uri = '/atlas/index.html';
  }

  return request;
}
```

Create this function in the CloudFront console under Functions, then associate it with the `/atlas/*` behavior as a "Viewer Request" function.

#### Step F: Update CORS on the API Gateway

Update the `AllowOrigins` in `template.yaml` to include your domain:

```yaml
CorsConfiguration:
  AllowHeaders:
    - Content-Type
    - Authorization
  AllowMethods:
    - GET
    - POST
    - PUT
    - DELETE
    - OPTIONS
  AllowOrigins:
    - 'https://yourdomain.com'
```

Also update the CORS headers in `src/utils.py`:

```python
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "https://yourdomain.com",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}
```

Redeploy: `sam build && sam deploy`

#### Step G: Update the S3 images bucket CORS

The images bucket also needs CORS for direct browser uploads. Update the `AllowedOrigins` in `template.yaml`:

```yaml
CorsConfiguration:
  CorsRules:
    - AllowedHeaders:
        - '*'
      AllowedMethods:
        - PUT
        - GET
        - HEAD
      AllowedOrigins:
        - 'https://yourdomain.com'
      MaxAge: 3600
```

Redeploy: `sam build && sam deploy`

#### Step H: Verify

1. Open `https://yourdomain.com/atlas` — you should see the Atlas login page
2. Log in with your credentials
3. Navigate around — the hash-based routing (`#/dashboard`, `#/portfolio`) works under any path
4. Create a watch, add expenses, upload images — verify the API calls go through `/atlas/api/`

#### Summary of what changed

| Component | Change |
|---|---|
| Existing CloudFront | Added 2 origins (S3 + API Gateway) and 2-3 cache behaviors |
| S3 upload path | Files uploaded under `atlas/` prefix instead of root |
| `frontend/index.html` | Added `<base href="/atlas/">` and set `ATLAS_API_URL` |
| `template.yaml` CORS | Changed `AllowOrigins` from `*` to your domain |
| `src/utils.py` CORS | Changed `Access-Control-Allow-Origin` to your domain |
| Route 53 | No changes needed — your existing A/AAAA alias record already points to the CloudFront distribution |

Your Route 53 record stays exactly the same. Since you're adding behaviors to the same CloudFront distribution, the existing DNS entry covers Atlas automatically.

#### Alternative: Subdomain approach (`atlas.yourdomain.com`)

If you'd prefer a subdomain instead of a subpath, the setup is simpler — you can use Atlas's own CloudFront distribution directly:

1. Add `atlas.yourdomain.com` as an alias on the Atlas CloudFront distribution in `template.yaml`
2. Add the ACM certificate ARN to the distribution's `ViewerCertificate`
3. Create a Route 53 A record (alias) for `atlas.yourdomain.com` pointing to the Atlas CloudFront distribution
4. Redeploy: `sam build && sam deploy`

This keeps Atlas fully isolated from your existing infrastructure.

### Monitoring and logs

```bash
# View Lambda logs in real-time
sam logs --stack-name atlas --tail

# View logs for a specific time range
sam logs --stack-name atlas --start-time "2024-01-01T00:00:00" --end-time "2024-01-02T00:00:00"

# View logs in CloudWatch console
# Go to: CloudWatch → Log groups → /aws/lambda/atlas-api-prod
```

### Cost estimate

Atlas uses pay-per-request pricing across all services. For a single-user app with light usage:

| Service | Estimated monthly cost |
|---|---|
| Lambda | ~$0.00 (free tier: 1M requests/month) |
| DynamoDB | ~$0.00 (free tier: 25 GB storage, 25 WCU/RCU) |
| S3 | ~$0.01-0.05 (storage + requests) |
| CloudFront | ~$0.00-0.10 (free tier: 1 TB transfer/month) |
| API Gateway | ~$0.00 (free tier: 1M requests/month) |
| Secrets Manager | ~$0.40 (1 secret × $0.40/month) |
| **Total** | **~$0.50/month** |

After the 12-month AWS free tier expires, costs remain minimal for single-user usage.

---

## Teardown

To completely remove Atlas from your AWS account:

```bash
# 1. Empty the S3 buckets (required before stack deletion)
WEB_BUCKET=$(aws cloudformation describe-stacks --stack-name atlas --query 'Stacks[0].Outputs[?OutputKey==`WebAssetsBucketName`].OutputValue' --output text)
IMAGE_BUCKET=$(aws cloudformation describe-stacks --stack-name atlas --query 'Stacks[0].Outputs[?OutputKey==`ImagesBucketName`].OutputValue' --output text)

aws s3 rm s3://$WEB_BUCKET --recursive
aws s3 rm s3://$IMAGE_BUCKET --recursive

# 2. Delete the CloudFormation stack (removes all resources)
sam delete --stack-name atlas

# 3. Optionally delete the secret (if you created it before deployment)
aws secretsmanager delete-secret \
  --secret-id atlas-secret-prod \
  --force-delete-without-recovery \
  --region us-east-1
```

---

## Troubleshooting

### `sam build` fails with Docker errors

Make sure Docker is running. SAM uses Docker to build Lambda packages in a Linux-compatible environment.

```bash
docker info  # Should show Docker is running
```

### `sam local start-api` returns 502 errors

Check that your `env.json` points to real AWS resources and your AWS credentials are valid. The local Lambda still needs to reach DynamoDB, S3, and Secrets Manager in your AWS account.

### Login fails after deployment

1. Verify the secret exists: `aws secretsmanager get-secret-value --secret-id atlas-secret-prod --region us-east-1`
2. Verify the secret name matches the Lambda environment variable: check `SECRET_NAME` in the Lambda console
3. Make sure the region in the secret matches the deployment region

### Frontend shows a blank page

1. Check the browser console for errors
2. Verify `window.ATLAS_API_URL` is set correctly
3. Verify the frontend files were uploaded: `aws s3 ls s3://$WEB_BUCKET/`
4. If you just deployed, wait a few minutes for CloudFront to propagate, or invalidate the cache

### CORS errors in the browser

The SAM template allows all origins (`*`) by default. If you've restricted it, make sure your CloudFront domain is in the `AllowOrigins` list in `template.yaml`.

### Tests fail locally

Make sure you're in the virtual environment and all dependencies are installed:

```bash
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest
```
