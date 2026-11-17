# Picomatch advisory assessment

[GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf) covers Picomatch through 4.0.7 and listed no fixed version on 2026-11-17. The npm bulk advisory identifier is 1247710. Both dependency audits failed on this one new record in [Foundation runtime 44179798419](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/44179798419) on `5b0bd895a8d7bc74445e99e396665ef7d524d9f7`. The job reported installed versions 2.3.1, 2.3.2 and 4.0.7.

The pinned Yarn dependency paths place Picomatch in provider tooling.

- Frappe's root lock and the realtime overlay resolve it via `anymatch`/`readdirp` for Chokidar and `micromatch` for `fast-glob`. The product web process uses Node's HTTP and child-process modules. The Frappe Socket.IO entry uses Socket.IO, Redis and cookie handling. The inspected installed-app realtime handlers do not import the glob tooling.
- Education's frontend resolves it through the file watcher and Tailwind's `fast-glob`/`micromatch` chain. `frontend_graph-result.json` in [Foundation artifact 14372483191](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/44179798419/artifacts/14372483191) records no rendered Picomatch code in the Education production build.
- The frozen HRMS frontend and Roster, and ERPNext Banking locks show the other consumers as file watching, Tailwind, `@rollup/pluginutils`, `tinyglobby` and Vite. The inspected upstream ERPNext, HRMS and Education root lockfiles contain no Picomatch edge. Payments has no root Yarn lock at the selected commit.

The provider build checks emitted application and global JavaScript and source maps for the known parser signature or its source-map module path. It then removes only the verified Picomatch directories from the staged bench before preparing assets and copying the bench into the customer image. This also removes the copies that Frappe's public `node_modules` aliases would otherwise expose. The signature is specific to the three npm parser versions whose SHA-256s are recorded in the build check. The Education Vite check also refuses any rendered module attributed to Picomatch. Packaging tests verify the guard and its placement after compilation and before publishing runtime assets.

The dated `BUILD_ONLY` disposition applies to the reviewed source and build path. It does not describe an upstream patch or authorize previously built binaries. Release acceptance still depends on the exact source passing Foundation, Product Image and the other applicable gates.
