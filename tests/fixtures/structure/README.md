# Captured structure responses

Captured directly from `https://api.trafa.se/api/structure` on 2026-10-25,
with the queries below and `lang=sv`. Files preserve the received response
bodies without trimming, anonymization, or reformatting. No live request is
made by tests. The local .gitignore exception includes these JSON fixtures
despite the repository-wide generated-JSON exclusion. The snapshot is deliberately fixed; new API years should not
silently change test expectations.

| File | Query | SHA-256 |
| --- | --- | --- |
| `t10011-agarkat.json` | `t10011|agarkat` | `ee4918e54ba8c292841f79ee6315e9d2a9f68e97d8cb2fc3883655beb5b557e8` |
| `t10011-ar.json` | `t10011|ar` | `bbcd9f02a3f225e6662f1e428047529412bfa3603eb6142bd7147739ebd151fe` |
| `t10011-tillst.json` | `t10011|tillst` | `ad9da97affe50c11bebc7f9fac5af85bd87f7b559d943b823fc1bcb104451435` |
| `t10011.json` | `t10011` | `9c40bdff14fd397b80862e6992534d70e583ff48fb8d3847ff20d734a23f9a9a` |

The `t10011` product has empty `StructureItems`. Its D, M and H entries are
top-level siblings linked by `ParentName=t10011`. The `agare` hierarchy
contains D entries `agarkat` and `tillst`; their DV values remain nested.
The received `tillst.ParentName` is `agarkat` even though it appears alongside
`agarkat` under `agare`. This is preserved, not normalized by the fixture.

Direct `t10011|ar`, `t10011|agarkat` and `t10011|tillst` responses include the
product catalogue and the product's other metadata too. The tests must select
the requested variable from that response, including recursively within H.
They assert exact values, labels, filters, descriptions and unique IDs, a
single direct query and no call to `_explore_variable_options_hierarchical`.
The two year filters have explicit null descriptions; numeric year values have
empty descriptions. Both forms are preserved in the expected output.

Derived defensive tests explicitly modify snapshots (missing/empty options,
unrelated product sibling), or use empty responses and a mocked fallback to
verify dispatch. A separate defensive test documents that the existing
fallback cannot build a hierarchy path from the captured flat product
structure. These cases are not claims that the live API reaches the fallback.
The previous synthetic nested-product success tests have been replaced;
production code, fallback implementation and coverage exclusions are unchanged.

These snapshots validate one product and three queries. They do not reproduce
the maintainer's survey of all hierarchical variables across every product.

Review context: https://github.com/xemarap/trafapy/pull/1#issuecomment-6399094366
