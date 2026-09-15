import json
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID


def test_azure_auth_requires_sign_in_and_explicit_user_allowlist() -> None:
    config_path = Path(__file__).resolve().parents[1] / "deploy" / "azure-auth.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))["properties"]

    assert config["platform"]["enabled"] is True
    assert config["httpSettings"]["requireHttps"] is True
    assert config["globalValidation"] == {
        "unauthenticatedClientAction": "RedirectToLoginPage",
        "redirectToProvider": "aad",
        "excludedPaths": [],
    }
    assert set(config["identityProviders"]) == {"azureActiveDirectory"}
    provider = config["identityProviders"]["azureActiveDirectory"]
    assert provider["enabled"] is True
    registration = provider["registration"]
    assert registration["clientSecretSettingName"] == "entra-client-secret"
    assert str(UUID(registration["clientId"])) == registration["clientId"]
    issuer = urlparse(registration["openIdIssuer"])
    assert issuer.scheme == "https"
    assert issuer.netloc == "login.microsoftonline.com"
    tenant_id, version = issuer.path.strip("/").split("/")
    assert str(UUID(tenant_id)) == tenant_id
    assert version == "v2.0"

    validation = provider["validation"]
    assert validation["allowedAudiences"] == [registration["clientId"]]
    policy = validation["defaultAuthorizationPolicy"]
    assert set(policy) == {"allowedPrincipals"}
    assert set(policy["allowedPrincipals"]) == {"identities"}
    identities = policy["allowedPrincipals"]["identities"]
    assert identities
    assert len(identities) == len(set(identities))
    for identity in identities:
        assert str(UUID(identity)) == identity
