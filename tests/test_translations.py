import ast
import os
import unittest

DASHBOARD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard.py")


def _tree():
    with open(DASHBOARD, encoding="utf-8") as f:
        return ast.parse(f.read())


def _load(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "_T_EN":
            return node.value
    raise AssertionError("_T_EN not found")


class TranslationDictionaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _tree()
        node = _load(cls.tree)
        cls.pairs = [(k.value, v.value) for k, v in zip(node.keys, node.values)]

    def test_no_conflicting_duplicate_keys(self):
        seen, conflicts = {}, set()
        for key, value in self.pairs:
            if key in seen and seen[key] != value:
                conflicts.add(key)
            seen[key] = value
        self.assertEqual(sorted(conflicts), [])

    def test_keys_are_not_dangerously_short(self):
        # _apply_translations does a plain str.replace over the whole page.
        legacy = {"Tag", "N/D"}
        short = [k for k, v in self.pairs if k != v and len(k) < 4 and k not in legacy]
        self.assertEqual(short, [])

    def test_translated_values_are_not_empty(self):
        self.assertEqual([k for k, v in self.pairs if not v.strip()], [])

    def test_required_entries_resolve_to_english(self):
        table = dict(self.pairs)
        required = {
            "Nessun router selezionato": "No router selected",
            "Backup già in corso": "A backup is already running",
            "Seleziona un file.": "Select a file.",
            "Rimuovere questa colonna?": "Remove this column?",
            "Errore di rete:": "Network error:",
            "REAL TIME MONITORING ATTIVO": "REAL TIME MONITORING ACTIVE",
            "Nessun sito": "No site",
        }
        for it, en in required.items():
            self.assertEqual(table.get(it), en)

    def test_static_t_calls_have_dictionary_entries(self):
        keys = {k for k, _ in self.pairs}
        # Strings that are intentionally identical in both languages.
        allowed = {"device", "Access Point"}
        missing = []
        for n in ast.walk(self.tree):
            if (isinstance(n, ast.Call) and getattr(n.func, "id", "") == "T" and n.args
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)
                    and n.args[0].value not in keys and n.args[0].value not in allowed):
                missing.append((n.lineno, n.args[0].value))
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
