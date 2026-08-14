#!/usr/bin/env python3
"""Adversarial test battery for the secret guard.

Two halves, and the second half matters more:

  MUST BLOCK  - real credentials, across all ten stacks in the estate.
  MUST ALLOW  - ordinary code that superficially resembles a credential.
                Placeholders, env references, hashes, high-entropy strings
                that are not secrets. A guard that trips on these gets
                switched off within a week, and then it protects nothing.

Run:  python3 tests/test_secret_guard.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import secret_guard  # noqa: E402


def token(*parts: str) -> str:
    """Assemble a credential-shaped string at runtime.

    The values below are fake, but they match the shapes real vendor scanners
    look for — so a literal in this file would trip GitHub push protection and
    block anyone who forks the repo. Joining the fragments here keeps the test
    exercising the exact same final string while leaving nothing scannable on
    disk. Any contributor adding a vendor case should do the same.
    """
    return "".join(parts)


def verdict(tool: str, tool_input: dict, cwd: str = "/tmp/estate-test") -> str:
    decision, _reason, _detail = secret_guard.decide(
        {"tool_name": tool, "tool_input": tool_input, "cwd": cwd}
    )
    return decision


# ---------------------------------------------------------------------------
# MUST BLOCK - real credential material
# ---------------------------------------------------------------------------

MUST_BLOCK: list[tuple[str, str, dict]] = [
    # -- Sensitive paths -----------------------------------------------------
    ("read .env", "Read", {"file_path": "/work/api/.env"}),
    ("read .env.production", "Read", {"file_path": "services/.env.production"}),
    ("write to .env", "Write", {"file_path": ".env", "content": "A=1"}),
    ("read private key", "Read", {"file_path": "certs/server.pem"}),
    ("read ssh key", "Read", {"file_path": "/Users/dev/.ssh/id_ed25519"}),
    ("read aws credentials", "Read", {"file_path": "/Users/dev/.aws/credentials"}),
    ("read kubeconfig", "Read", {"file_path": "/Users/dev/.kube/config"}),
    ("read npmrc", "Read", {"file_path": "/Users/dev/.npmrc"}),
    ("read java keystore", "Read", {"file_path": "android/app/release.keystore"}),
    ("read ios profile", "Read", {"file_path": "ios/Runner.mobileprovision"}),
    ("read terraform state", "Read", {"file_path": "infra/terraform.tfstate"}),
    ("read as400 profile", "Read", {"file_path": "as400/ftp.cfg"}),

    # -- Bash reaching for secrets ------------------------------------------
    ("cat .env", "Bash", {"command": "cat .env"}),
    ("source .env", "Bash", {"command": "source .env && npm start"}),
    ("grep the env file", "Bash", {"command": "grep API_KEY .env.local"}),
    ("cat aws creds", "Bash", {"command": "cat ~/.aws/credentials"}),
    ("base64 a key", "Bash", {"command": "base64 -i certs/private.pem"}),
    ("env dump filtered", "Bash", {"command": "env | grep SECRET"}),
    ("printenv filtered", "Bash", {"command": "printenv | grep -i token"}),

    # -- Vendor credential shapes in written content ------------------------
    ("aws key in Node config", "Write", {
        "file_path": "src/config.js",
        "content": 'export const AWS_KEY = "' + token("AKIA", "IOSFODNN7EXAMPLE") + '";',
    }),
    ("github token in shell", "Bash", {
        "command": "git remote set-url origin "
                   "https://" + token("ghp", "_16CharsAndThenSomeMoreCharsToPad12345")
                   + "@github.com/a/b",
    }),
    ("slack token in Java", "Write", {
        "file_path": "src/main/java/Notify.java",
        "content": 'String hook = "' + token("xoxb", "-2401234567", "-2412345678901",
                                  "-AbCdEfGhIjKlMnOp") + '";',
    }),
    ("google api key in Kotlin", "Write", {
        "file_path": "app/src/main/kotlin/Maps.kt",
        "content": 'val key = "' + token("AIza", "SyD-9tSrke72PouQMnMX-a7eZSW0jkFMBWY") + '"',
    }),
    ("stripe live key in .NET", "Write", {
        "file_path": "Services/Billing.cs",
        "content": 'const string Key = "' + token("sk_", "live_", "4eC39HqLyjWDarjtT1zdp7dc")
                   + '";',
    }),
    ("anthropic key in Python", "Write", {
        "file_path": "app.py",
        "content": 'client = Anthropic(api_key="' + token("sk-", "ant-", "api03-") +
                   'aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789")',
    }),
    ("private key block in Rust", "Write", {
        "file_path": "src/tls.rs",
        "content": 'const K: &str = "-----BEGIN RSA PRIVATE KEY-----\\nMIIE...";',
    }),
    ("db url with password in Swift", "Write", {
        "file_path": "Sources/Config.swift",
        "content": 'let dsn = "postgres://admin:Hunter2Hunter2@db.internal:5432/app"',
    }),
    ("jwt in BrightScript", "Write", {
        "file_path": "components/Auth.brs",
        "content": 'token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.'
                   'eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ.'
                   'dQw4w9WgXcQ1234567890abcdef"',
    }),
    ("azure account key in config", "Write", {
        "file_path": "appsettings.json",
        "content": '"Storage": "DefaultEndpointsProtocol=https;AccountKey='
                   'abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQ=="',
    }),
    ("npm token in CI file", "Write", {
        "file_path": ".github/workflows/publish.yml",
        "content": "NODE_AUTH_TOKEN: " + token("npm", "_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"),
    }),
    ("generic high-entropy password", "Write", {
        "file_path": "src/main/resources/application.properties",
        "content": "spring.datasource.password=xK9$mQ2vL8pR4wZ7nT5bY3",
    }),
    ("client secret in React env", "Write", {
        "file_path": "src/auth.ts",
        "content": 'const client_secret = "' + token("GOCSPX", "-aB3dEfGh1JkLmN0pQrStUvWx")
                   + '"',
    }),
]

# ---------------------------------------------------------------------------
# MUST ALLOW - ordinary code that looks alarming but is not a leak
# ---------------------------------------------------------------------------

MUST_ALLOW: list[tuple[str, str, dict]] = [
    # -- Safe variants of sensitive paths ------------------------------------
    ("env example file", "Read", {"file_path": ".env.example"}),
    ("env sample file", "Read", {"file_path": "config/.env.sample"}),
    ("ssh known_hosts", "Read", {"file_path": "/Users/dev/.ssh/known_hosts"}),
    ("ssh config", "Read", {"file_path": "/Users/dev/.ssh/config"}),
    ("ordinary source file", "Read", {"file_path": "src/main/java/App.java"}),
    ("a file named environment.ts", "Read", {"file_path": "src/environment.ts"}),

    # -- Env references, not values -----------------------------------------
    ("node env reference", "Write", {
        "file_path": "src/config.js",
        "content": "const apiKey = process.env.API_KEY;",
    }),
    ("python env reference", "Write", {
        "file_path": "settings.py",
        "content": 'SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]',
    }),
    ("java env reference", "Write", {
        "file_path": "Config.java",
        "content": 'String token = System.getenv("SERVICE_TOKEN");',
    }),
    ("dotnet config reference", "Write", {
        "file_path": "Startup.cs",
        "content": 'var secret = Configuration["ClientSecret"];',
    }),
    ("shell var interpolation", "Bash", {
        "command": 'curl -H "Authorization: Bearer ${API_TOKEN}" https://api.x/v1',
    }),
    ("yaml vault reference", "Write", {
        "file_path": "k8s/deploy.yaml",
        "content": "password: ${VAULT_DB_PASSWORD}",
    }),
    ("secret manager reference", "Write", {
        "file_path": "infra/main.tf",
        "content": 'password = data.aws_secretsmanager_secret_version.db.secret_string',
    }),

    # -- Placeholders --------------------------------------------------------
    ("docs placeholder", "Write", {
        "file_path": "README.md",
        "content": 'export API_KEY="your-api-key-here"',
    }),
    ("angle bracket placeholder", "Write", {
        "file_path": "docs/setup.md",
        "content": "password: <YOUR_PASSWORD>",
    }),
    ("changeme default", "Write", {
        "file_path": "docker-compose.yml",
        "content": "POSTGRES_PASSWORD: changeme_in_production",
    }),
    ("template mustache", "Write", {
        "file_path": "chart/values.yaml",
        "content": "apiKey: {{ .Values.global.apiKey }}",
    }),
    ("redacted in a log", "Write", {
        "file_path": "docs/troubleshooting.md",
        "content": 'Authorization: Bearer ****************redacted',
    }),

    # -- High entropy that is not a secret -----------------------------------
    ("git sha in changelog", "Write", {
        "file_path": "CHANGELOG.md",
        "content": "Fixed in commit a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
    }),
    ("lockfile integrity hash", "Write", {
        "file_path": "package-lock.json",
        "content": '"integrity": "sha512-'
                   'K5mDTBpTNGTa9pNBiBcuT9StGpZLtJUmMd2rW6Vx1sB0uV+g/0kZ1F7wRp=="',
    }),
    ("uuid constant", "Write", {
        "file_path": "src/ids.ts",
        "content": 'export const TENANT_ID = "f47ac10b-58cc-4372-a567-0e02b2c3d479";',
    }),
    ("base64 image data", "Write", {
        "file_path": "src/logo.ts",
        "content": 'const logo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg";',
    }),
    ("css class soup in React", "Write", {
        "file_path": "src/App.tsx",
        "content": '<div className="flex min-h-screen flex-col items-center">',
    }),
    ("public url no credentials", "Write", {
        "file_path": "src/api.ts",
        "content": 'const BASE = "https://api.example.com/v2/payments";',
    }),

    # -- Words that trigger naive scanners -----------------------------------
    ("password field definition", "Write", {
        "file_path": "src/models/User.java",
        "content": "private String password;  // hashed with bcrypt before store",
    }),
    ("token type enum", "Write", {
        "file_path": "src/auth/types.ts",
        "content": 'export type TokenKind = "access_token" | "refresh_token";',
    }),
    ("test asserting on a key name", "Write", {
        "file_path": "tests/config.test.js",
        "content": 'expect(config).toHaveProperty("apiKey");',
    }),
    ("brightscript registry read", "Write", {
        "file_path": "components/Auth.brs",
        "content": 'token = RegRead("access_token", "auth")',
    }),
    ("as400 program call", "Write", {
        "file_path": "src/Bridge.java",
        "content": 'ProgramCall pc = new ProgramCall(as400, "/QSYS.LIB/PAYLIB.LIB");',
    }),
    ("ordinary bash build", "Bash", {"command": "./gradlew clean build -x test"}),
    ("bash reading a normal config", "Bash", {"command": "cat config/app.yaml"}),
    ("git status", "Bash", {"command": "git status --short"}),

    # -- The hard ones: expressions assigned to credential-shaped names ------
    # These are where naive scanners fall apart, because the variable name
    # matches and the value is long. The value is code, not a credential.
    ("password from a function call", "Write", {
        "file_path": "src/auth.js",
        "content": "const password = hashPassword(userInput, saltRounds);",
    }),
    ("kotlin keystore lookup", "Write", {
        "file_path": "app/src/main/kotlin/Crypto.kt",
        "content": "val privateKey = keyStore.getKey(alias, passphrase.toCharArray())",
    }),
    ("java secret from builder", "Write", {
        "file_path": "src/main/java/Client.java",
        "content": "String clientSecret = credentialsProvider.resolveSecret();",
    }),
    ("rust token from struct field", "Write", {
        "file_path": "src/client.rs",
        "content": "let auth_token = self.config.auth_token.clone();",
    }),
    ("swift keychain read", "Write", {
        "file_path": "Sources/Keychain.swift",
        "content": "let apiKey = try keychain.readString(forKey: .serviceApiKey)",
    }),
    ("dotnet secret from options", "Write", {
        "file_path": "Services/Auth.cs",
        "content": "var clientSecret = _options.Value.ClientSecret;",
    }),
    ("python token from method", "Write", {
        "file_path": "client.py",
        "content": "access_token = self._session.fetch_access_token(scope)",
    }),
    ("stripe TEST key is not a live key", "Write", {
        "file_path": "tests/billing.test.js",
        "content": 'const key = "' + token("sk_", "test_", "51H8xY2KZvMnBqR3tGhJkLmNoPqRsTuVw")
                   + '";',
    }),
    ("csp nonce", "Write", {
        "file_path": "src/middleware/csp.ts",
        "content": 'res.setHeader("Content-Security-Policy", `nonce-${rAnd0mN0nc3V4lu3}`)',
    }),
    ("ternary default", "Write", {
        "file_path": "src/config.ts",
        "content": "const apiKey = process.env.API_KEY ?? defaultDevelopmentKey;",
    }),
    ("secret name in a log message", "Write", {
        "file_path": "src/logger.go",
        "content": 'log.Warn("client_secret missing from configuration payload")',
    }),
    ("brightscript field assignment", "Write", {
        "file_path": "components/Login.brs",
        "content": 'm.top.findNode("auth").token = m.global.sessionToken',
    }),
]


class SecretGuardPrecision(unittest.TestCase):
    def test_blocks_real_credentials(self) -> None:
        missed = [
            name for name, tool, ti in MUST_BLOCK
            if verdict(tool, ti) != "deny"
        ]
        self.assertEqual([], missed, f"{len(missed)} credential(s) not blocked")

    def test_allows_ordinary_code(self) -> None:
        tripped = [
            name for name, tool, ti in MUST_ALLOW
            if verdict(tool, ti) != "allow"
        ]
        self.assertEqual(
            [], tripped, f"{len(tripped)} false positive(s) - people will "
                         f"switch the guard off"
        )


def report() -> int:
    """Print the precision/recall table the docs quote."""
    caught = [(n, t, i) for n, t, i in MUST_BLOCK if verdict(t, i) == "deny"]
    missed = [(n, t, i) for n, t, i in MUST_BLOCK if verdict(t, i) != "deny"]
    clean = [(n, t, i) for n, t, i in MUST_ALLOW if verdict(t, i) == "allow"]
    tripped = [(n, t, i) for n, t, i in MUST_ALLOW if verdict(t, i) != "allow"]

    print("\nEstate Agent secret guard - measured behaviour")
    print("=" * 58)
    print(f"  Real credentials blocked   {len(caught):>3}/{len(MUST_BLOCK)}"
          f"   (recall {len(caught) / len(MUST_BLOCK):.0%})")
    print(f"  Ordinary code allowed      {len(clean):>3}/{len(MUST_ALLOW)}"
          f"   (false positive rate {len(tripped) / len(MUST_ALLOW):.0%})")

    if missed:
        print("\n  MISSED credentials:")
        for name, _t, _i in missed:
            print(f"    - {name}")
    if tripped:
        print("\n  FALSE POSITIVES:")
        for name, tool, ti in tripped:
            _d, reason, _x = secret_guard.decide(
                {"tool_name": tool, "tool_input": ti, "cwd": "/tmp"})
            print(f"    - {name}: {reason.splitlines()[0]}")
    print()
    return 1 if (missed or tripped) else 0


if __name__ == "__main__":
    if "--report" in sys.argv:
        sys.exit(report())
    unittest.main(verbosity=2)
