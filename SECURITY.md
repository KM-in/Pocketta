# Security policy

## Supported version

Only the current `main` branch is supported during the hackathon.

## Reporting

Do not publicly disclose issues that could expose recordings, transcripts, secrets, or arbitrary local files. Contact the maintainers privately through the repository host's security-reporting channel with reproduction steps, affected revision, impact, and mitigation ideas. Never include real private lecture data.

## Security model

PocketTA is a single-user localhost application, not a hardened multi-user service. It restricts LM Studio endpoints to loopback; optional cloud processing sends selected text and images to the server-configured `CEREBRAS_BASE_URL`, which defaults to the HTTPS Cerebras API endpoint. The configured endpoint receives the provider API key, so use a trusted destination and HTTPS for remote services. Keys remain server-side. It avoids shell command construction, randomizes data directories, and supports permanent deletion. Users remain responsible for OS access controls, disk encryption, runtime updates, recording consent, and checking generated material.
