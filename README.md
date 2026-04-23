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
├── Makefile                        # Dev and deploy commands (make help)
├── requirements.txt                # Runtime dependencies
└── requirements-dev.txt            # Dev/test dependencies
```

---

## Running Locally

All common tasks are available through `make`. Run `make help` to see everything.

### Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.12+ | `brew install python@3.12` or [python.org](https://www.python.org/downloads/) |
| AWS SAM CLI | Latest | `brew install aws-sam-cli` or [install guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) |
| Docker | Latest | Required by `sam local`. [Get Docker](https://docs.docker.com/get-docker/) |
| AWS CLI v2 | Latest | `brew install awscli` (only needed for deployment) |

### Quick start

```bash
git clone <repo-url>
cd atlas

python3.12 -m venv .venv
source .venv/bin/activate

make install    # Install all dependencies
make test       # Run unit + integration tests (fast, no AWS needed)
make dev        # Start frontend (:8080) + backend (:3000)
```

That's it. Open http://localhost:8080 in your browser.

To connect the frontend to the local API, uncomment the `ATLAS_API_URL` line in `frontend/index.html`, or set it in the browser console:

```javascript
window.ATLAS_API_URL = "http://127.0.0.1:3000";
```

> The local backend (`sam local start-api`) uses Docker to emulate Lambda and needs real AWS credentials to reach DynamoDB, S3, and Secrets Manager. Make sure `aws configure` is set up and you've run `make secrets` at least once.

### Available make targets

| Command | What it does |
|---|---|
| `make install` | Install all Python dependencies |
| `make test` | Run unit + integration tests (fast) |
| `make test-all` | Run full suite including property-based tests |
| `make coverage` | Run tests with HTML coverage report |
| `make dev` | Start frontend + backend together |
| `make frontend` | Start only the frontend on port 8080 |
| `make backend` | Build SAM and start the local API on port 3000 |
| `make build` | Build the SAM application |
| `make clean` | Remove build artifacts and caches |

### Customizing ports

```bash
make dev FRONTEND_PORT=9090 API_PORT=4000
```

### Running against deployed AWS resources

If you've already deployed the stack and want the local API to use those resources:

Create an `env.json` file:

```json
{
  "AtlasFunction": {
    "TABLE_NAME": "atlas-table-prod",
    "IMAGE_BUCKET_NAME": "atlas-images-<account-id>-prod",
    "SECRET_NAME": "atlas-secret-prod"
  }
}
```

Then start the backend with:

```bash
sam build && sam local start-api --env-vars env.json
```

### Development workflow

1. Edit source code in `src/`
2. Run relevant tests: `make test` (or `pytest tests/unit/test_watch_service.py -v`)
3. Test the full app: `make dev`
4. Run the full suite before committing: `make test-all`

---

## Production Deployment

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

### First-time deploy

```bash
# 1. Configure AWS credentials
aws configure

# 2. Install dependencies (if you haven't already)
make install

# 3. Run tests to verify everything works
make test

# 4. Provision the auth secret (interactive — prompts for username/password)
make secrets

# 5. First deploy (interactive — prompts for stack config, saves to samconfig.toml)
make deploy-first

# 6. Set the API URL in frontend/index.html (see output from step 5)
#    Uncomment and update the ATLAS_API_URL line, then:
make upload
```

During `make deploy-first`, use these recommended values:

| Prompt | Recommended value |
|---|---|
| Stack Name | `atlas` |
| AWS Region | Same region as your secret (e.g. `us-east-1`) |
| Parameter StageName | `prod` |
| Confirm changes before deploy | `y` |
| Allow SAM CLI IAM role creation | `y` |
| Disable rollback | `n` |
| Save arguments to configuration file | `y` |

Deployment takes 3-5 minutes. CloudFront distribution creation can take up to 15 minutes on the first deploy.

### Subsequent deploys

```bash
make deploy             # Backend changes (build + deploy)
make upload             # Frontend-only changes (S3 sync + CloudFront invalidation)
```

### Useful deployment commands

| Command | What it does |
|---|---|
| `make deploy` | Build and deploy backend to AWS |
| `make deploy-first` | First-time guided deploy (interactive) |
| `make upload` | Upload frontend to S3 + invalidate CloudFront |
| `make secrets` | Create or update the auth secret |
| `make outputs` | Show deployed stack outputs (API URL, buckets, etc.) |

### Stack outputs

After deploying, view your resource info anytime:

```bash
make outputs
```

| Output | Purpose |
|---|---|
| `ApiEndpoint` | API URL — set this in `frontend/index.html` |
| `WebDistributionUrl` | Your app's public HTTPS URL |
| `WebDistributionId` | For cache invalidation |
| `WebAssetsBucketName` | Where frontend files are hosted |
| `ImagesBucketName` | Where watch images are stored |
| `AtlasTableName` | DynamoDB table name |
| `AtlasSecretArn` | Secret ARN |

### Changing your password

```bash
make secrets
```

The change takes effect immediately — no redeployment needed.

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
