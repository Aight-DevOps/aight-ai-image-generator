# aight-ai-image-generator (refactoring branch)

A standalone Python toolkit for AI-driven image and video generation, registration, and quality review. Leverages Stable Diffusion SDXL, AWS services (S3, DynamoDB, Lambda), and Streamlit for web UI.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Repository Structure](#repository-structure)
3. [Module Descriptions](#module-descriptions)
4. [Prerequisites](#prerequisites)
5. [Environment Setup](#environment-setup)
6. [Configuration Files](#configuration-files)
7. [AWS Setup Guide](#aws-setup-guide)
8. [Usage](#usage)
   - [Image Generation](#image-generation)
   - [Image Registration (CLI)](#image-registration-cli)
   - [Image Review (Web UI)](#image-review-web-ui)
9. [Troubleshooting & FAQ](#troubleshooting--faq)
10. [Development & Customization](#development--customization)
11. [Performance & Maintenance](#performance--maintenance)
12. [Security Considerations](#security-considerations)
13. [License](#license)

---

## Project Overview

This toolkit provides three core capabilities:

- **Image Generation**: Batch generation of anime-style “beautiful girl” images via SDXL, with prompt randomization, LoRA integration, ControlNet, and Bedrock comment support.
- **Image Registration**: CLI tool to register locally generated images and metadata to AWS S3/DynamoDB, with Bedrock comment generation.
- **Image Review**: Streamlit web UI for reviewers to approve/reject images, display metadata, LoRA details, multi-timeslot comments, and statistics.

Built-in versioning; centralized configuration; robust error handling; extensible modular architecture.

---

## Repository Structure

```text
aight-ai-image-generator/
├── common/ # Shared utilities (logger, AWS client manager, config manager, types)
├── config/ # YAML configuration files
│ ├── config_v10.yaml # Core generation & posting settings
│ ├── generation_types.yaml
│ ├── hybrid_bijo_register_config.yaml
│ ├── prompts.yaml
│ └── random_elements.yaml
├── image_generator/ # SDXL image generation tool
│ ├── core/ # Generator engine, model manager, saver
│ ├── prompt/ # Prompt builder, LoRA & pose managers
│ ├── processing/ # Image processor, engine
│ ├── randomization/ # SecureRandom, ImagePool, element generator
│ └── main.py # CLI entrypoint for generation
├── image_register/ # Image registration CLI tool
│ ├── core/ # Main register logic
│ ├── scanner/ # FileScanner for image+metadata pairs
│ ├── converter/ # MetadataConverter, TypeConverter
│ ├── uploader/ # S3Uploader, DynamoDBUploader
│ ├── processor/ # BatchProcessor with delay
│ └── main.py # CLI menu entrypoint
├── image_reviewer/ # Streamlit web UI for image review
│ ├── core/ # ImageReviewSystem orchestrator
│ ├── data/ # DataLoader, DataParser
│ ├── display/ # ImageViewer, UIComponents
│ ├── review/ # CommentManager, RejectionHandler, StatusUpdater
│ ├── stats/ # StatsAnalyzer
│ └── main.py # Streamlit app entrypoint
├── requirements.txt # Python dependencies
└── README.md
```

---

## Module Descriptions

- **common/**:

  - `logger.py`: Colored console logging.
  - `aws_client.py`: AWS S3/DynamoDB/Lambda client management.
  - `config_manager.py`: YAML config loading with defaults.
  - `timer.py`: ProcessTimer utility.
  - `types.py`: Shared data classes (e.g., `GenerationType`).

- **config/**: Centralized settings for generation, registration, review, logging, error handling, performance, and business rules.

- **image_generator/**: Entire image generation pipeline (prompt assembly, engine execution, saving, metadata).

- **image_register/**: CLI tool to register images & metadata to AWS, generate Bedrock comments, handle retries, cleanup.

- **image_reviewer/**: Streamlit-based review UI with tabs for inspection, statistics, system info; full-featured metadata display and comment/time-slot management.

---

## Prerequisites

- Python 3.8+
- AWS account with IAM credentials (access to S3, DynamoDB, Lambda)
- Stable Diffusion WebUI or API endpoint
- Git

---

## Environment Setup

```text
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Configuration Files

- **`config/config_v10.yaml`**: Core settings for image generation, SDXL, ControlNet, ADetailer, SNS/Slack, posting rules, quality, performance.
- **`config/hybrid_bijo_register_config.yaml`**: Settings for registration tool (AWS region, directories, error handling, Bedrock).
- **`config/prompts.yaml`, `config/random_elements.yaml`, `config/generation_types.yaml`**: Prompt templates, random element lists, per-genre generation types.

_Edit these YAML files to suit your environment and workflow._

---

## AWS Setup Guide

1. **Create S3 bucket** (e.g., `aight-media-images`).
2. **Create DynamoDB table** (e.g., `AightMediaImageData`) with partition key `imageId` (String).
3. **Deploy Lambda** for Bedrock comment generation (`aight-bedrock-comment-generator`).
4. **Configure IAM role** granting S3, DynamoDB, and Lambda invoke permissions.

---

## Usage

### Image Generation

```text
# Generate images of the "normal" genre by CUI menyu by batch
cd image_generator
python3 -m image_generator.main normal 5
```

```text
# Generate images of the "normal" genre by CUI menu
cd image_generator
python3 -m image_generator.main normal 5
```

### Image Registration (CLI)

```text
# Register images in the "normal" directory
cd image_register
python3 -m image_register.main

Follow the interactive menu to select genre and execute batch
```

### Image Review (Web UI)

```text
# Launch Streamlit app
cd image_reviewer
streamlit run main.py
```

Access http://localhost:8501 in your browser.

---

## Troubleshooting & FAQ

- **“ModuleNotFoundError” after renaming files**: Update all `import` paths to match new file/folder names.
- **Streamlit “missing ScriptRunContext” warning**: Ignore when running as script; use `streamlit run`.
- **Bedrock comment failures**: Check Lambda permissions, API rate limits, and `bedrock.lambda_function_name` in config.

---

## Development & Customization

- **Add new generation types**: Edit `config/generation_types.yaml` and update prompts.
- **Customize prompts**: Modify `config/prompts.yaml` and `config/random_elements.yaml`.
- **Extend review rules**: Update `image_reviewer/review/comment_manager.py` or `rejection_handler.py`.

---

## Performance & Maintenance

- Adjust `performance.concurrent_generations` and `api_rate_limit` in `config_v10.yaml`.
- Monitor CloudWatch logs for AWS errors.
- Clean up old images via DynamoDB TTL or S3 lifecycle policies.

---

## Security Considerations

- Store AWS credentials securely (env vars or IAM roles).
- Do not commit sensitive config (e.g., real webhook URLs) to public repos.
- Use IAM least-privilege for Lambda and DynamoDB access.

---

## License

MIT License

---
