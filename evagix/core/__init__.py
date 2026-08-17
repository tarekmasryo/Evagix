"""Core contracts and infrastructure shared by Evagix layers.

The package intentionally avoids eager imports so low-level modules such as
`evagix.utils` can depend on `evagix.core.io` without circular imports.
Import concrete models from `evagix.core.models` directly.
"""

__all__: list[str] = []
