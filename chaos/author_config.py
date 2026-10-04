"""Model-authoring provider and model configuration (NGPL; see dat/license).

Neither the provider nor the model is hard-coded. Each comes from a flag or an
environment variable: the flag wins, then the variable, then the default,
which is none. An empty variable counts as unset. With nothing configured
there is no model content and nothing here touches the network or a ledger.

API keys come only from the user's environment at run time. This module reads
a key variable's *name* from configuration and never reads, stores or prints
the key itself; backends read the value when they are built.
"""

from dataclasses import dataclass
import re

PROVIDER_FLAG = "--author-provider"
PROVIDER_ENV = "NYARLATHACK_AUTHOR_PROVIDER"
MODEL_FLAG = "--author-model"
MODEL_ENV = "NYARLATHACK_AUTHOR_MODEL"
KEY_ENV_FLAG = "--api-key-env"

# provider -> standard key variable for API-key providers, None for OAuth
# providers (Hermes holds their credential; NyarlatHack holds no key).
PROVIDERS = {
    "xai-oauth": None,
    "xai": "XAI_API_KEY",
    "openai-codex": None,
}

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")


class AuthorConfigError(ValueError):
    """Invalid authoring configuration. Messages are fixed text naming only
    flags and variables, never a supplied value, so they are safe to print."""


@dataclass(frozen=True)
class AuthorConfig:
    provider: str
    model: str
    key_env: str | None  # variable NAME for API-key providers; never a key

    @property
    def oauth(self):
        return PROVIDERS[self.provider] is None

    def record(self):
        """The choice-record form: names only, never a credential."""
        return {"provider": self.provider, "model": self.model, "key_env": self.key_env}


def _value(flag_value, env, name):
    if flag_value is not None:
        return flag_value
    value = env.get(name)
    return value if value else None


def resolve(provider=None, model=None, api_key_env=None, env=None):
    """Return an AuthorConfig, or None when nothing is configured.

    provider/model/api_key_env are the flag values (None when not given);
    env is the environment mapping (pass {} to ignore the environment).
    """
    env = {} if env is None else env
    provider = _value(provider, env, PROVIDER_ENV)
    model = _value(model, env, MODEL_ENV)
    if provider is None and model is None:
        if api_key_env is not None:
            raise AuthorConfigError(
                f"{KEY_ENV_FLAG} needs an API-key provider: set {PROVIDER_FLAG} "
                f"or {PROVIDER_ENV}, and {MODEL_FLAG} or {MODEL_ENV}"
            )
        return None
    if provider is None:
        raise AuthorConfigError(
            f"a model is configured without a provider: set {PROVIDER_FLAG} "
            f"or {PROVIDER_ENV}"
        )
    if provider not in PROVIDERS:
        raise AuthorConfigError(
            f"unknown provider in {PROVIDER_FLAG} / {PROVIDER_ENV}; "
            "expected one of: " + ", ".join(PROVIDERS)
        )
    if model is None:
        raise AuthorConfigError(
            f"a provider is configured without a model: set {MODEL_FLAG} "
            f"or {MODEL_ENV} (a model id is never guessed)"
        )
    if not _MODEL.fullmatch(model):
        raise AuthorConfigError(
            f"invalid model id in {MODEL_FLAG} / {MODEL_ENV}: use letters, "
            "digits and . _ : / - (at most 128 characters)"
        )
    standard = PROVIDERS[provider]
    if standard is None:
        if api_key_env is not None:
            raise AuthorConfigError(
                f"{KEY_ENV_FLAG} applies only to API-key providers; "
                f"{provider} is an OAuth provider and holds no key"
            )
        key_env = None
    else:
        key_env = standard if api_key_env is None else api_key_env
        if not _NAME.fullmatch(key_env):
            raise AuthorConfigError(
                f"{KEY_ENV_FLAG} must name an environment variable "
                "(letters, digits and underscores), never hold a key"
            )
    return AuthorConfig(provider, model, key_env)


def from_record(record):
    """Rebuild a recorded configuration; fails closed on anything malformed."""
    if record is None:
        return None
    if type(record) is not dict or set(record) != {"provider", "model", "key_env"}:
        raise ValueError("invalid recorded author configuration")
    provider, model, key_env = record["provider"], record["model"], record["key_env"]
    if (
        type(provider) is not str
        or provider not in PROVIDERS
        or type(model) is not str
        or not _MODEL.fullmatch(model)
    ):
        raise ValueError("invalid recorded author configuration")
    if PROVIDERS[provider] is None:
        if key_env is not None:
            raise ValueError("invalid recorded author configuration")
    elif type(key_env) is not str or not _NAME.fullmatch(key_env):
        raise ValueError("invalid recorded author configuration")
    return AuthorConfig(provider, model, key_env)


def add_arguments(parser):
    parser.add_argument(
        PROVIDER_FLAG,
        dest="author_provider",
        help=f"model-authoring provider ({', '.join(PROVIDERS)}); overrides "
        f"{PROVIDER_ENV}; default none (no model content)",
    )
    parser.add_argument(
        MODEL_FLAG,
        dest="author_model",
        help=f"model-authoring model id; overrides {MODEL_ENV}; never guessed",
    )
    parser.add_argument(
        KEY_ENV_FLAG,
        dest="api_key_env",
        help="API-key providers only: NAME of the environment variable holding "
        "the key (default: the provider's standard name, e.g. XAI_API_KEY); "
        "never the key itself",
    )


def require_provider(config, provider):
    """For callers that support exactly one provider today."""
    if config is None:
        raise AuthorConfigError(
            f"this command needs a model: set {PROVIDER_FLAG} / {PROVIDER_ENV} "
            f"and {MODEL_FLAG} / {MODEL_ENV}"
        )
    if config.provider != provider:
        raise AuthorConfigError(
            f"this command supports only {PROVIDER_FLAG} {provider}"
        )
    return config
