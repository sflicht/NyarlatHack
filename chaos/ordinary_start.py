"""Ordinary Bard start identity. No wizard mode and no model call."""

OPTIONS = (
    "name:ChaosReview,role:Bard,race:human,gender:male,align:neutral,"
    "pettype:dog,windowtype:tty,!news,!legacy,time,!splash_screen,"
    "!perm_invent,!autopickup"
)


def reject_wizard_args(game_args):
    """Refuse debug/wizard tokens; ordinary play is not wizard mode."""
    lowered = [str(arg) for arg in game_args]
    if "-D" in lowered or "-debug" in lowered:
        raise ValueError("ordinary start refuses wizard mode")
    for index, arg in enumerate(lowered):
        if arg == "-u" and index + 1 < len(lowered):
            if lowered[index + 1].lower() == "wizard":
                raise ValueError("ordinary start refuses wizard mode")
        if arg.lower() in ("-uwizard", "--wizard"):
            raise ValueError("ordinary start refuses wizard mode")
