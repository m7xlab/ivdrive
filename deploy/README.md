# Deploying with pre-built images

`compose.prebuilt.yml` is a production template that pulls the published multi-architecture (amd64 and arm64) images from Docker Hub instead of building them:

- `m7xlab/ivdrive-api`, `m7xlab/ivdrive-collector`, `m7xlab/ivdrive-web`

Copy it next to your `.env`, set `IVDRIVE_VERSION` (for example `v1.4.1`), and follow the upgrade order in the [self-hosting guide](../docs/self-hosting.md#upgrading): back up, run the migrations, then start the new containers.

The template was written for an earlier release. Compare its services and environment variables with the repository's `docker-compose.yml` and [`.env.example`](../.env.example) before using it, and check the release notes of the version you pick.
