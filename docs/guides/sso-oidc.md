# SSO and OIDC Mapping

HAL's first SSO/OIDC slice maps verified identity claims into the research OS
user and team model. Token verification still belongs in the gateway or HTTP
adapter that receives requests; HAL's shared service layer accepts already
verified claims and converts them into durable users, roles, and memberships.

## Configuration

```yaml
hal9000:
  auth:
    enabled: true
    provider: oidc
    oidc_issuer_url: https://issuer.example.com/
    oidc_audience: hal-9000
    email_claim: email
    subject_claim: sub
    name_claim: name
    groups_claim: groups
    admin_groups:
      - hal:admins
    team_group_prefix: "hal:"
```

Environment variables use the same nested settings names:

```bash
HAL9000_AUTH__ENABLED=true
HAL9000_AUTH__OIDC_ISSUER_URL=https://issuer.example.com/
HAL9000_AUTH__OIDC_AUDIENCE=hal-9000
HAL9000_AUTH__ADMIN_GROUPS='["hal:admins"]'
HAL9000_AUTH__TEAM_GROUP_PREFIX=hal:
```

## Claim Mapping

The mapper expects claims after signature, issuer, audience, expiration, and
nonce checks have already succeeded.

```python
from hal9000.research.identity import OIDCIdentityMapper

result = OIDCIdentityMapper(store, settings.auth).map_claims(
    {
        "sub": "stable-subject",
        "email": "researcher@example.com",
        "name": "Researcher",
        "groups": ["hal:materials", "hal:admins"],
    }
)
```

Mapping behavior:

- `email` identifies the HAL user.
- `sub` is stored as `external_subject` and must remain stable.
- `name` updates the display name.
- Any group in `admin_groups` maps the user to global `admin`.
- Groups matching `team_group_prefix` create or reuse HAL teams and add the user
  as a team member.
- Existing team roles are preserved during group sync.

## CLI Smoke Test

For local adapter testing:

```bash
hal research map-oidc-user \
  --claims-json '{"sub":"s1","email":"researcher@example.com","name":"Researcher","groups":["hal:materials"]}'
```

## Adapter Boundary

Production adapters should:

1. Fetch and cache the provider JWKS.
2. Verify token signature and algorithm.
3. Verify issuer, audience, expiration, and nonce where applicable.
4. Pass verified claims into `OIDCIdentityMapper`.
5. Use `ResearchAuthorizer` or higher-level services for project permissions.
