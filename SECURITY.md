# Security policy

## Supported version

Only the current `main` branch is supported during the hackathon.

## Reporting

Do not publicly disclose issues that could expose recordings, transcripts, secrets, or arbitrary local files. Contact the maintainers privately through the repository host's security-reporting channel with reproduction steps, affected revision, impact, and mitigation ideas. Never include real private lecture data.

## Security model

PocketTA is a single-user localhost application, not a hardened multi-user service. It restricts LM Studio endpoints to loopback; optional Cerebras processing sends selected text and images to the fixed HTTPS Cerebras API endpoint. Keys remain server-side. It avoids shell command construction, randomizes data directories, and supports permanent deletion. Users remain responsible for OS access controls, disk encryption, runtime updates, recording consent, and checking generated material.
