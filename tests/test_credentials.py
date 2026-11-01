import ast
import os
import unittest
from unittest import mock

DASHBOARD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard.py")

_NAMES = {
    "_cred_set_username", "_make_credential", "_cred_set_to_credential", "_resolve_credential",
    "_resolve_cred_id", "_get_credential_for_site", "_get_creds_for_site", "_get_device_credential",
    "_get_device_creds", "_ssh_auth_kwargs", "_ssh_connect_cred", "_ssh_connect", "_ssh_connect_creds",
}


def _load_namespace():
    with open(DASHBOARD, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    ns = {"CRED_TYPE_PASSWORD": "password", "SSH_TIMEOUT": 7}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _NAMES:
            exec(compile(ast.Module([node], []), DASHBOARD, "exec"), ns)
    return ns


class CredentialResolutionTests(unittest.TestCase):
    def setUp(self):
        self.ns = _load_namespace()
        self.ns["_decrypt"] = lambda s: s[4:] if s.startswith("enc:") else s
        self.ns["CRED_SETS"] = [
            {"id": "cs_1", "name": "a", "username_enc": "enc:admin", "password_enc": "enc:pw"},
            {"id": "cs_2", "name": "legacy", "username": "old", "password_enc": "enc:pw2"},
        ]
        self.ns["SITES"] = {"s1": {"credential_id": "cs_1"}}
        self.ns["DEVICES"] = {}

    def test_missing_type_is_password(self):
        cred = self.ns["_resolve_credential"]("cs_1")
        self.assertEqual(cred, {"type": "password", "username": "admin", "password": "pw"})

    def test_legacy_plaintext_username(self):
        self.assertEqual(self.ns["_resolve_cred_id"]("cs_2"), ("old", "pw2"))

    def test_unknown_or_empty_id(self):
        self.assertEqual(self.ns["_resolve_cred_id"]("nope"), ("", ""))
        self.assertEqual(self.ns["_resolve_cred_id"](""), ("", ""))

    def test_site_credential(self):
        self.assertEqual(self.ns["_get_creds_for_site"]("s1"), ("admin", "pw"))
        self.assertEqual(self.ns["_get_creds_for_site"]("missing"), ("", ""))

    def test_device_priority(self):
        d = self.ns["DEVICES"]
        d["1.1.1.1"] = {"credential_id": "cs_2", "ssh_user": "u", "ssh_pass_enc": "enc:p", "site_id": "s1"}
        d["2.2.2.2"] = {"ssh_user": "u", "ssh_pass_enc": "enc:p", "site_id": "s1"}
        d["3.3.3.3"] = {"site_id": "s1"}
        d["4.4.4.4"] = {"credential_id": "gone", "site_id": "s1"}
        get = self.ns["_get_device_creds"]
        self.assertEqual(get("1.1.1.1"), ("old", "pw2"))
        self.assertEqual(get("2.2.2.2"), ("u", "p"))
        self.assertEqual(get("3.3.3.3"), ("admin", "pw"))
        self.assertEqual(get("4.4.4.4"), ("admin", "pw"))
        self.assertEqual(get("9.9.9.9"), ("", ""))


class SshConnectTests(unittest.TestCase):
    def setUp(self):
        self.ns = _load_namespace()
        self.paramiko = mock.MagicMock()
        self.ns["paramiko"] = self.paramiko
        self.client = self.paramiko.SSHClient.return_value

    def test_password_connect_arguments_unchanged(self):
        self.ns["_ssh_connect_creds"]("10.0.0.1", "admin", "pw")
        self.client.connect.assert_called_once_with(
            "10.0.0.1", timeout=7, look_for_keys=False, allow_agent=False,
            banner_timeout=9, auth_timeout=9, username="admin", password="pw")

    def test_read_connect_uses_device_credential(self):
        self.ns["_get_device_credential"] = lambda ip: {"type": "password", "username": "u", "password": "p"}
        self.ns["_ssh_connect"]("10.0.0.2")
        kwargs = self.client.connect.call_args.kwargs
        self.assertEqual((kwargs["username"], kwargs["password"]), ("u", "p"))

    def test_unsupported_type_rejected(self):
        with self.assertRaises(ValueError):
            self.ns["_ssh_auth_kwargs"]({"type": "bogus"})


if __name__ == "__main__":
    unittest.main()
