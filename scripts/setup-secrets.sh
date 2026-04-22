#!/usr/bin/env bash
#
# setup-secrets.sh — Provision the Atlas authentication secret in AWS Secrets Manager.
#
# Creates (or updates) the Secrets Manager secret with:
#   - username
#   - bcrypt password hash (cost factor 12)
#   - random JWT signing key
#
# Prerequisites:
#   - AWS CLI v2 configured with valid credentials
#   - Python 3 with bcrypt installed (pip install bcrypt)
#
# Usage:
#   ./scripts/setup-secrets.sh
#

set -euo pipefail

# ── Defaults ──
DEFAULT_USERNAME="admin"
DEFAULT_REGION="us-east-1"
DEFAULT_STAGE="prod"

# ── Prompt for inputs ──
read -rp "Username [$DEFAULT_USERNAME]: " USERNAME
USERNAME="${USERNAME:-$DEFAULT_USERNAME}"

while true; do
    read -rsp "Password: " PASSWORD
    echo
    if [ -z "$PASSWORD" ]; then
        echo "Password cannot be empty. Please try again."
    else
        read -rsp "Confirm password: " PASSWORD_CONFIRM
        echo
        if [ "$PASSWORD" != "$PASSWORD_CONFIRM" ]; then
            echo "Passwords do not match. Please try again."
        else
            break
        fi
    fi
done

read -rp "AWS region [$DEFAULT_REGION]: " REGION
REGION="${REGION:-$DEFAULT_REGION}"

read -rp "Stage name [$DEFAULT_STAGE]: " STAGE
STAGE="${STAGE:-$DEFAULT_STAGE}"

SECRET_NAME="atlas-secret-${STAGE}"

echo ""
echo "Generating bcrypt hash (cost factor 12)..."

# Generate bcrypt hash using Python
PASSWORD_HASH=$(python3 -c "
import bcrypt, sys
password = sys.argv[1].encode('utf-8')
hashed = bcrypt.hashpw(password, bcrypt.gensalt(rounds=12))
print(hashed.decode('utf-8'))
" "$PASSWORD")

# Generate a random JWT signing key (32 bytes, base64-encoded)
JWT_SIGNING_KEY=$(python3 -c "
import secrets, base64
key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8')
print(key)
")

# Build the secret JSON
SECRET_VALUE=$(python3 -c "
import json, sys
print(json.dumps({
    'username': sys.argv[1],
    'passwordHash': sys.argv[2],
    'jwtSigningKey': sys.argv[3]
}))
" "$USERNAME" "$PASSWORD_HASH" "$JWT_SIGNING_KEY")

echo "Creating/updating secret '$SECRET_NAME' in region '$REGION'..."

# Try to create the secret; if it already exists, update it
if aws secretsmanager describe-secret \
    --secret-id "$SECRET_NAME" \
    --region "$REGION" \
    > /dev/null 2>&1; then

    aws secretsmanager put-secret-value \
        --secret-id "$SECRET_NAME" \
        --secret-string "$SECRET_VALUE" \
        --region "$REGION"

    echo "Secret '$SECRET_NAME' updated."
else
    aws secretsmanager create-secret \
        --name "$SECRET_NAME" \
        --description "Atlas authentication credentials" \
        --secret-string "$SECRET_VALUE" \
        --region "$REGION"

    echo "Secret '$SECRET_NAME' created."
fi

echo ""
echo "Done. Secret contents:"
echo "  Username:        $USERNAME"
echo "  Password hash:   ${PASSWORD_HASH:0:20}..."
echo "  JWT signing key: ${JWT_SIGNING_KEY:0:20}..."
echo ""
echo "You can now deploy Atlas with: sam build && sam deploy"
