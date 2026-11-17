"""Resolve existing forum tags without automatically creating label tags."""

REQUIRED_TAGS = ("Issue", "PR", "Open", "Closed", "Merged")


def resolve_tags(kind, state, labels, available, overrides=None):
    overrides = overrides or {}
    names = {tag.name.casefold(): tag for tag in available}
    ids = {tag.id: tag for tag in available}
    result = []
    for index, name in enumerate(
        [kind, state, *[x["name"] if isinstance(x, dict) else x for x in labels]]
    ):
        tag = (
            ids.get(overrides[name])
            if index >= 2 and name in overrides
            else names.get(name.casefold())
        )
        if tag and tag not in result:
            result.append(tag)
    return result[:5]
