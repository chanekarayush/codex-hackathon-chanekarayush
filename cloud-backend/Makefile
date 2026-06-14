.PHONY: build check-aws deploy deploy-guided teardown clean release refresh upload_ui outputs validate

# Fix Homebrew Python/libexpat linking issue on macOS.
HOMEBREW_PREFIX ?= /opt/homebrew
HOMEBREW_EXPAT_PREFIX := $(shell brew --prefix expat 2>/dev/null)
HOMEBREW_EXPAT_LIB := $(if $(strip $(HOMEBREW_EXPAT_PREFIX)),$(HOMEBREW_EXPAT_PREFIX)/lib,$(HOMEBREW_PREFIX)/opt/expat/lib)
export DYLD_LIBRARY_PATH := $(HOMEBREW_PREFIX)/lib:$(HOMEBREW_EXPAT_LIB):$(DYLD_LIBRARY_PATH)
AWS := DYLD_LIBRARY_PATH="$(DYLD_LIBRARY_PATH)" aws
SAM := DYLD_LIBRARY_PATH="$(DYLD_LIBRARY_PATH)" sam

ifneq (,$(wildcard ../.env))
include ../.env
export
endif

TEMPLATE_FILE ?= template.yaml
STACK_NAME    ?= codex-project-backend
AWS_REGION    ?= $(shell $(AWS) configure get region 2>/dev/null)
AWS_REGION    := $(if $(strip $(AWS_REGION)),$(strip $(AWS_REGION)),us-east-1)
PROJECT_NAME  ?= codex_project
STAGE_NAME    ?= prod

VIDEO_DYNAMO_TABLE       := $(or $(strip $(VIDEO_DYNAMO_TABLE)),$(strip $(DITTO_VIDEOS_TABLE)),codex_project-content)
BOOK_DYNAMO_TABLE        := $(or $(strip $(BOOK_DYNAMO_TABLE)),$(strip $(DITTO_BOOKS_TABLE)),codex_project-books)
VIDEO_QDRANT_COLLECTION  := $(or $(strip $(VIDEO_QDRANT_COLLECTION)),$(strip $(VIDEO_COLLECTION_NAME)),codex_project-videos)
CREATE_DYNAMO_TABLES     ?= true
HF_EMBEDDING_MODEL       := $(or $(strip $(HF_EMBEDDING_MODEL)),BAAI/bge-m3)

FRONTEND_DIR ?= ../frontend
UI_FALLBACK_DIR ?= ui

PARAMETER_OVERRIDES = \
	ProjectName=$(PROJECT_NAME) \
	StageName=$(STAGE_NAME) \
	CreateDynamoTables=$(CREATE_DYNAMO_TABLES) \
	VideoMetadataTableName=$(VIDEO_DYNAMO_TABLE) \
	BooksMetadataTableName=$(BOOK_DYNAMO_TABLE) \
	VideoCollectionName=$(VIDEO_QDRANT_COLLECTION) \
	QdrantUrl=$(QDRANT_URL) \
	QdrantApiKey=$(QDRANT_API_KEY) \
	HfApiKey=$(HF_API_KEY) \
	HfEmbeddingModel=$(HF_EMBEDDING_MODEL)

validate:
	@echo "Validating SAM template..."
	@$(SAM) validate -t $(TEMPLATE_FILE) --region $(AWS_REGION)

build:
	@echo "Building SAM application..."
	@$(SAM) build -t $(TEMPLATE_FILE)

check-aws:
	@echo "Checking AWS CLI connectivity and credentials for $(AWS_REGION)..."
	@TMP_ERR=$$(mktemp); \
	if ! $(AWS) sts get-caller-identity --region $(AWS_REGION) --output json >/dev/null 2>$$TMP_ERR; then \
		cat $$TMP_ERR; \
		if grep -Eqi "pyexpat|libexpat|Symbol not found|dlopen" $$TMP_ERR; then \
			echo "AWS CLI is crashing before it can contact AWS. This is usually a broken Homebrew awscli/Python/expat install."; \
			echo "Fix the local aws command first, then rerun make check-aws."; \
		else \
			echo "AWS CLI could not connect or authenticate. Check internet/VPN/proxy, AWS credentials, and AWS_REGION=$(AWS_REGION)."; \
		fi; \
		rm -f $$TMP_ERR; \
		exit 1; \
	fi; \
	rm -f $$TMP_ERR
	@TMP_ERR=$$(mktemp); \
	if ! $(AWS) cloudformation list-stacks --region $(AWS_REGION) --max-items 1 --output json >/dev/null 2>$$TMP_ERR; then \
		cat $$TMP_ERR; \
		echo "AWS CloudFormation endpoint is not reachable or your identity cannot call cloudformation:ListStacks in $(AWS_REGION)."; \
		rm -f $$TMP_ERR; \
		exit 1; \
	fi; \
	rm -f $$TMP_ERR

deploy: check-aws build
	@echo "Deploying SAM application..."
	@$(SAM) deploy \
		--stack-name $(STACK_NAME) \
		--region $(AWS_REGION) \
		--resolve-s3 \
		--capabilities CAPABILITY_IAM \
		--no-confirm-changeset \
		--no-fail-on-empty-changeset \
		--parameter-overrides $(PARAMETER_OVERRIDES)

deploy-guided: check-aws build
	@echo "Deploying SAM application in guided mode..."
	@$(SAM) deploy --guided \
		--stack-name $(STACK_NAME) \
		--region $(AWS_REGION) \
		--capabilities CAPABILITY_IAM \
		--parameter-overrides $(PARAMETER_OVERRIDES)

release: check-aws build
	@echo "Releasing $(STACK_NAME) to $(AWS_REGION)..."
	@$(SAM) deploy \
		--stack-name $(STACK_NAME) \
		--region $(AWS_REGION) \
		--resolve-s3 \
		--capabilities CAPABILITY_IAM \
		--no-confirm-changeset \
		--no-fail-on-empty-changeset \
		--parameter-overrides $(PARAMETER_OVERRIDES)
	@$(MAKE) upload_ui
	@$(MAKE) outputs

refresh: check-aws build
	@echo "Refreshing backend stack..."
	@$(SAM) deploy \
		--stack-name $(STACK_NAME) \
		--region $(AWS_REGION) \
		--resolve-s3 \
		--capabilities CAPABILITY_IAM \
		--no-confirm-changeset \
		--no-fail-on-empty-changeset \
		--parameter-overrides $(PARAMETER_OVERRIDES)
	@$(MAKE) upload_ui

upload_ui: check-aws
	@echo "Uploading UI assets..."
	@UI_BUCKET=$$($(AWS) cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--region $(AWS_REGION) \
		--query "Stacks[0].Outputs[?OutputKey=='UiBucketName'].OutputValue" \
		--output text 2>/dev/null || echo "") ; \
	if [ -z "$$UI_BUCKET" ] || [ "$$UI_BUCKET" = "None" ]; then \
		echo "UI bucket not found. Deploy the stack first."; \
		exit 1; \
	fi; \
	if [ -f "$(FRONTEND_DIR)/package.json" ]; then \
		echo "Building frontend from $(FRONTEND_DIR)..."; \
		cd $(FRONTEND_DIR) && if [ -f package-lock.json ]; then npm ci; else npm install; fi && npm run build; \
		SOURCE_DIR="$(FRONTEND_DIR)/dist"; \
	else \
		echo "No frontend package found. Uploading placeholder UI from $(UI_FALLBACK_DIR)."; \
		SOURCE_DIR="$(UI_FALLBACK_DIR)"; \
	fi; \
	$(AWS) s3 sync "$$SOURCE_DIR" "s3://$$UI_BUCKET" --delete --exclude "config.json" --region $(AWS_REGION); \
	API_URL=$$($(AWS) cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--region $(AWS_REGION) \
		--query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
		--output text 2>/dev/null || echo "") ; \
	if [ -n "$$API_URL" ] && [ "$$API_URL" != "None" ]; then \
		TMP_CONFIG=$$(mktemp); \
		printf '{\n  "projectName": "%s",\n  "apiUrl": "%s"\n}\n' "$(PROJECT_NAME)" "$$API_URL" > "$$TMP_CONFIG"; \
		$(AWS) s3 cp "$$TMP_CONFIG" "s3://$$UI_BUCKET/config.json" \
			--content-type "application/json" \
			--cache-control "no-store" \
			--region $(AWS_REGION) >/dev/null; \
		rm -f "$$TMP_CONFIG"; \
		echo "Uploaded runtime config.json for $$API_URL"; \
	fi; \
	CF_DIST_ID=$$($(AWS) cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--region $(AWS_REGION) \
		--query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" \
		--output text 2>/dev/null || echo "") ; \
	if [ -n "$$CF_DIST_ID" ] && [ "$$CF_DIST_ID" != "None" ]; then \
		echo "Invalidating CloudFront cache $$CF_DIST_ID..."; \
		$(AWS) cloudfront create-invalidation --distribution-id "$$CF_DIST_ID" --paths "/*" >/dev/null; \
	fi

outputs:
	@$(SAM) list stack-outputs --stack-name $(STACK_NAME) --region $(AWS_REGION)

teardown:
	@echo "Tearing down $(STACK_NAME)..."
	@UI_BUCKET=$$($(AWS) cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--region $(AWS_REGION) \
		--query "Stacks[0].Outputs[?OutputKey=='UiBucketName'].OutputValue" \
		--output text 2>/dev/null || echo "") ; \
	if [ -n "$$UI_BUCKET" ] && [ "$$UI_BUCKET" != "None" ]; then \
		echo "Emptying UI bucket $$UI_BUCKET..."; \
		$(AWS) s3 rm "s3://$$UI_BUCKET" --recursive --region $(AWS_REGION) || true; \
	fi
	@$(SAM) delete --stack-name $(STACK_NAME) --region $(AWS_REGION) --no-prompts
	@$(MAKE) clean

clean:
	@echo "Cleaning local SAM build artifacts..."
	rm -rf .aws-sam
