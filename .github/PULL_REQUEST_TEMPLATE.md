<!-- Title as a Conventional Commit, e.g. "fix: keep @Key entries out of Fields validation". -->

## What and why

<!-- One paragraph. Link the issue with "Closes #123" when there is one. -->

## How it was verified

<!-- Which tests were added or changed. Say explicitly whether the change was tried against a real
     AFAS environment; CI cannot, so a human may need to. -->

## Checklist

- [ ] `./workflow.cmd lint`, `test` and `quality` pass locally
- [ ] Docs updated (`docs/reference/tools.md`, `docs/reference/configuration.md`, how-to pages) where behaviour changed
- [ ] No token, member id or other credential anywhere in the diff
- [ ] Writing to AFAS is still impossible without `AFAS_ALLOW_WRITES=true`
- [ ] Any new dependency has a permissive license (MIT, BSD, Apache, PSF, ISC)
