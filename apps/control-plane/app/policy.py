from dataclasses import dataclass
DESTRUCTIVE = ("delete", "destroy", "purge", "terminate", "drop database", "rm -rf", "format ", "revoke", "wipe", "reset", "terraform apply", "kubectl delete", "git push --force", "shutdown", "reboot", "payment", "purchase", "transfer money", "deploy to production")
MEDIUM = ("deploy", "apply", "restart", "scale", "install", "uninstall", "modify", "change", "send email", "post", "publish", "upload")
@dataclass(frozen=True)
class Assessment:
    risk: str
    requires_approval: bool
    reason: str
def assess(text: str) -> Assessment:
    text = text.lower()
    if hit := next((x for x in DESTRUCTIVE if x in text), None):
        return Assessment("HIGH", True, f"Approval required: {hit}")
    if hit := next((x for x in MEDIUM if x in text), None):
        return Assessment("MEDIUM", False, f"Evidence required: {hit}")
    return Assessment("LOW", False, "Low-impact or read-only task")
