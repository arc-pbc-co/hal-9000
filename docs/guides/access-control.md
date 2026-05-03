# Access Control

HAL now has the first database-backed identity and permission layer for the
firm-wide research OS. This is the foundation for SSO/OIDC integration, API
authorization, review UI permissions, and audit views.

## Concepts

| Concept | Purpose |
|---------|---------|
| User | A firm account identified by normalized email and optional SSO subject. |
| Team | A firm group that can receive project-level access. |
| Membership | A user-to-team link with a team role such as `member` or `manager`. |
| Project permission | A direct user or team grant on a research project. |

Project roles are ordered from least to most privileged:

1. `viewer`
2. `contributor`
3. `reviewer`
4. `admin`

Users with the global role `admin` can access all projects. Other users receive
access from direct project grants and active team memberships.

## CLI Setup

Create a user:

```bash
hal research create-user researcher@example.com \
  --display-name "Researcher"
```

Create a team:

```bash
hal research create-team materials --name "Materials"
```

Add the user to the team:

```bash
hal research add-team-member materials researcher@example.com --role member
```

Grant project access to a team:

```bash
hal research grant-project-access firm-research \
  --team-slug materials \
  --role reviewer \
  --granted-by admin@example.com
```

Grant project access directly to a user:

```bash
hal research grant-project-access firm-research \
  --user-email researcher@example.com \
  --role contributor \
  --granted-by admin@example.com
```

## Implementation Boundary

This slice creates the durable governance substrate. API route enforcement,
SSO/OIDC token mapping, review UI affordances, and audit dashboards should build
on these tables rather than adding separate identity state.
