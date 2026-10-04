"""Model-authoring configuration: flag > environment > none; every rejection.

Offline. No provider is imported or contacted.
"""

import unittest

from chaos.author_config import (
    MODEL_ENV,
    PROVIDER_ENV,
    AuthorConfig,
    AuthorConfigError,
    from_record,
    require_provider,
    resolve,
)

MODEL = "grok-test-model"  # fixture id; real runs pass --author-model


class ResolveTests(unittest.TestCase):
    def test_nothing_configured_is_none(self):
        self.assertIsNone(resolve())
        self.assertIsNone(resolve(env={}))
        # An empty variable counts as unset.
        self.assertIsNone(resolve(env={PROVIDER_ENV: "", MODEL_ENV: ""}))

    def test_flags(self):
        config = resolve("xai-oauth", MODEL)
        self.assertEqual(config, AuthorConfig("xai-oauth", MODEL, None))
        self.assertTrue(config.oauth)

    def test_environment(self):
        env = {PROVIDER_ENV: "xai-oauth", MODEL_ENV: MODEL}
        self.assertEqual(resolve(env=env), AuthorConfig("xai-oauth", MODEL, None))

    def test_flag_beats_environment(self):
        env = {PROVIDER_ENV: "openai-codex", MODEL_ENV: "env-model"}
        self.assertEqual(
            resolve("xai-oauth", MODEL, env=env), AuthorConfig("xai-oauth", MODEL, None)
        )
        # Each setting falls back independently.
        self.assertEqual(
            resolve("xai-oauth", None, env=env),
            AuthorConfig("xai-oauth", "env-model", None),
        )
        self.assertEqual(
            resolve(None, MODEL, env=env), AuthorConfig("openai-codex", MODEL, None)
        )

    def test_empty_variable_falls_through_to_flag_or_none(self):
        env = {PROVIDER_ENV: "", MODEL_ENV: MODEL}
        with self.assertRaises(AuthorConfigError):
            resolve(env=env)  # model without provider
        self.assertEqual(
            resolve("xai-oauth", env=env), AuthorConfig("xai-oauth", MODEL, None)
        )

    def test_api_key_provider_standard_variable_and_override(self):
        self.assertEqual(resolve("xai", MODEL).key_env, "XAI_API_KEY")
        self.assertEqual(resolve("xai", MODEL, "MY_XAI_KEY").key_env, "MY_XAI_KEY")
        self.assertFalse(resolve("xai", MODEL).oauth)

    def test_rejections_name_flag_and_variable_never_the_value(self):
        secretish = "VALUE-THAT-MUST-NOT-ECHO"
        cases = [
            (dict(model=MODEL), ("--author-provider", PROVIDER_ENV)),
            (dict(provider="xai-oauth"), ("--author-model", MODEL_ENV)),
            (
                dict(provider=secretish, model=MODEL),
                ("--author-provider", PROVIDER_ENV),
            ),
            (
                dict(provider="xai-oauth", model="bad model!"),
                ("--author-model", MODEL_ENV),
            ),
            (
                dict(provider="xai-oauth", model=MODEL, api_key_env="XAI_API_KEY"),
                ("--api-key-env",),
            ),
            (
                dict(provider="openai-codex", model=MODEL, api_key_env="X"),
                ("--api-key-env",),
            ),
            (
                dict(provider="xai", model=MODEL, api_key_env="not a name"),
                ("--api-key-env",),
            ),
            (dict(provider="xai", model=MODEL, api_key_env="1BAD"), ("--api-key-env",)),
            (dict(api_key_env="XAI_API_KEY"), ("--api-key-env", PROVIDER_ENV)),
        ]
        for kwargs, names in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(AuthorConfigError) as caught:
                    resolve(env={}, **kwargs)
                text = str(caught.exception)
                for name in names:
                    self.assertIn(name, text)
                self.assertNotIn(secretish, text)
                self.assertNotIn("bad model!", text)
                self.assertNotIn("not a name", text)

    def test_unknown_provider_from_environment(self):
        with self.assertRaises(AuthorConfigError):
            resolve(env={PROVIDER_ENV: "anthropic", MODEL_ENV: MODEL})

    def test_require_provider(self):
        with self.assertRaises(AuthorConfigError):
            require_provider(None, "openai-codex")
        with self.assertRaises(AuthorConfigError):
            require_provider(resolve("xai-oauth", MODEL), "openai-codex")
        config = resolve("openai-codex", MODEL)
        self.assertIs(require_provider(config, "openai-codex"), config)


class RecordTests(unittest.TestCase):
    def test_round_trip(self):
        for config in (
            resolve("xai-oauth", MODEL),
            resolve("xai", MODEL),
            resolve("xai", MODEL, "OTHER_KEY_VAR"),
            resolve("openai-codex", MODEL),
        ):
            self.assertEqual(from_record(config.record()), config)
        self.assertIsNone(from_record(None))

    def test_record_holds_names_only(self):
        self.assertEqual(
            resolve("xai", MODEL).record(),
            {"provider": "xai", "model": MODEL, "key_env": "XAI_API_KEY"},
        )

    def test_malformed_records_fail_closed(self):
        good = {"provider": "xai", "model": MODEL, "key_env": "XAI_API_KEY"}
        for bad in (
            [],
            {},
            dict(good, extra=1),
            dict(good, provider="other"),
            dict(good, model=""),
            dict(good, key_env=None),
            dict(good, key_env="no spaces allowed"),
            dict(good, provider="xai-oauth"),  # OAuth carries no key variable
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    from_record(bad)


class CommandTests(unittest.TestCase):
    """The ChatGPT OAuth commands need a configured openai-codex model and
    stop, with a message naming flags and variables, before any provider or
    ledger is touched."""

    def run_main(self, argv, env):
        import contextlib
        import io
        from unittest.mock import patch

        from chaos.__main__ import main

        err = io.StringIO()
        with (
            patch.dict("os.environ", env, clear=False),
            patch("chaos.oauth.native_client", side_effect=AssertionError("provider")),
            contextlib.redirect_stderr(err),
        ):
            for name in (PROVIDER_ENV, MODEL_ENV):
                if name not in env:
                    import os

                    os.environ.pop(name, None)
            code = main(argv)
        return code, err.getvalue()

    def test_oauth_commands_require_configuration(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            commands = (
                ["oauth", "--run-dir", directory, "--ledger", str(ledger)],
                [
                    "history",
                    "--run-dir",
                    directory,
                    "--backend",
                    "oauth",
                    "--model-ledger",
                    str(ledger),
                ],
            )
            for argv in commands:
                for extra, env, expected in (
                    ([], {}, "--author-provider"),
                    (
                        ["--author-provider", "xai-oauth", "--author-model", MODEL],
                        {},
                        "openai-codex",
                    ),
                    ([], {MODEL_ENV: MODEL}, PROVIDER_ENV),
                ):
                    with self.subTest(argv=argv[0], extra=extra, env=env):
                        code, err = self.run_main(argv + extra, env)
                        self.assertEqual(code, 2)
                        self.assertIn(expected, err)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
