# SNO hardware validation handoff

This is a test record and handoff guide, not a claim that installation has passed.
The revised tutorial is in
[`tutorials/setup-openshift-single-node/01.en.md`](../tutorials/setup-openshift-single-node/01.en.md).

## Scope and provenance

The implementation is based on PR #1492's head `ce119d99369d0803d3bb93dc846ced20f4eae291`.
It selectively reworks the proposed changes preserved at
`sno-review-fixes` (`56b5e17584478c03e0108f7416fde720fb682009`).
It does not update either source branch or the existing PR.

Retained ideas: real Hetzner resolver addresses, explicit hostname/SSH-key helper
arguments, complete API/apps DNS coverage, actual console/OAuth route discovery,
and a corrected local-storage documentation destination.

Additional changes: common DNS preflight, explicit IPv4 firewall rules, safer
disk targeting, fail-fast downloads with mandatory checksums for both archives,
protected off-host credential/state export, guarded initrd creation and kernel
handoff, and operator checks that reject degraded or incomplete responses.

This branch contains AI-assisted changes for the author's review and hardware
validation. Before publication, review the repository's
[`contributing.md`](../contributing.md), including its restrictions on primarily
AI-generated submissions and small external repositories. Keeping the optional
helper in a published article remains a maintainer decision; pinning it does not
waive that rule. The manual instructions remain self-contained.

## What has and has not been exercised

The offline tests execute selected Bash/Python snippets taken directly from the
tutorial, using temporary fixtures. Downloads, archive extraction, binary
installation, the external helper, DNS, `oc`, and `kexec` are replaced at their
boundaries. Actual checksum calculations and initrd byte concatenation are tested.
All Bash blocks are syntax-checked after example-placeholder substitution.

These tests do **not** establish that Cargo builds on the actual rescue OS, that
the selected OpenShift mirror artifacts are available, that the installer accepts
the complete configuration, that a kernel boots, or that OAuth login works.
The `4.22.1` string in unit tests is fixture input, not a release recommendation.

Run the offline suite from the repository root on Linux with Bash, GNU coreutils,
and Python 3. It needs no Python packages and no cluster credentials:

```bash
python3 tests/test_sno_tutorial.py
```

Do not run the whole article as a script. Follow its steps interactively and stop
after any error. Only the test suite is intended for unattended execution.

## Record the environment before installation

Keep the record private until addresses, identifiers, and logs have been reviewed.
Never include the pull secret, kubeconfig, kubeadmin password, cookies, or tokens.

| Field | Record for this run |
| ----- | ------------------- |
| Tutorial branch and commit | PENDING |
| Test date/time and preparation path | PENDING |
| Server model, CPU, RAM | PENDING |
| Rescue `/etc/os-release` and `uname -r` | PENDING |
| Firmware mode and Secure Boot/lockdown status | PENDING |
| Exact OpenShift version and installer release-image digest | PENDING |
| `oc` and `nmstatectl` versions | PENDING |
| Install disk by-id path and serial | PENDING |
| Non-target disks and their pre-test layout | PENDING |
| Primary NIC, MAC, IP/prefix, gateway | PENDING |
| DNS resolvers and public/private zone arrangement | PENDING |
| Robot incoming/outgoing rules and admin public IP | PENDING |
| Helper SHA, when used | `08615305502e22ebb1fd1f8bb9eb27281a681a27` |

Use an exact release available from the Red Hat mirror. Do not substitute a
moving `latest` directory or silently change releases between the two paths.

## First run: manual preparation

Use a disposable lab server with explicit permission to erase the selected disk,
verified backups, and KVM access available. Preserve the state of unrelated disks.
Leave optional CSI boot-disk reservation out of this baseline run.

| Gate | Required evidence | Result |
| ---- | ----------------- | ------ |
| Firewall | New SSH session works; explicit IPv4 rules; intended admin IP | PENDING |
| Disk target | By-id target and serial agree; no in-use devices; backups exist | PENDING |
| DNS before install | Both configured resolvers answer all preflight names; workstation resolves real routes | PENDING |
| Toolchain | Both archive checksums pass; exact versions recorded; Cargo build succeeds | PENDING |
| Config validation | `agent create pxe-files` accepts the edited configs | PENDING |
| Export | Archive copied to workstation; both auth files readable; existing kubeconfig untouched | PENDING |
| Boot | `kexec -l` succeeds; explicit BOOT confirmation; RHCOS reaches the expected NIC/IP | PENDING |
| Installation | One Ready node; converged cluster version; all operator checks pass | PENDING |
| Console/OAuth | Browser completes login and loads the authenticated console | PENDING |
| Disk outcome | Installed system maps to the intended serial; non-target layouts unchanged | PENDING |

The original maintainer-reported failure was at the console/OAuth stage.
A Ready node, successful `oc` commands, or an HTTP 200 health endpoint does not
close that issue. Record the actual browser result and exact error when it fails.

Keep the tutorial's validation-status warning until a fresh result is recorded.
Do not mark the helper path passed based on a manual-path success.

## Second run: optional helper preparation

After recording the manual run, deliberately prepare a fresh test environment.
Do not automatically wipe or retry a failed host. Preserve its evidence first.
Run the common disk/network/package steps, then the pinned helper recipe and the
same credential-export, boot, and acceptance steps.

Important details verified by inspecting the pinned helper's source:

- Its cleanup guard requires `INSTALL_DIR` to be underneath `WORKDIR`. The recipe
  uses `/root/ocp-prepare/install` beneath `/root/ocp-prepare` for both paths.
- Its dry-run calls `save_config`, writing `/root/.sno-prepare.conf`; do not
  describe it as write-free.
- Its prepare script does not perform the final `kexec` handoff. The revised
  article installs `kexec-tools` in the common steps and uses its own explicit
  boot block for both paths.
- The pinned helper's `--ip-family v4` selects the IPv4 configuration but does not
  emit the manual template's explicit `ipv6: {enabled: false}` stanza. Inspect
  the resulting network state and document differences; the two paths are not
  asserted to produce byte-identical YAML.
- Preparation prints administrative credentials. Do not paste its complete
  output into a public issue. Its source YAML backups are copied into the
  protected install directory before the common export step.

The helper is unchanged in its own repository. Its full execution was not part
of the offline tests. If it fails, record the pinned SHA, exact non-secret
arguments, failing stage, and sanitized error separately from manual-path results.

## Capture diagnostics without changing cluster configuration

On the workstation, set `KUBECONFIG` to the private export from the current run.
Create a private diagnostic directory. The following commands read cluster
resources/logs and write only local files; they do not create debug pods or
modify cluster settings:

```bash
umask 077
OUT=$(mktemp -d "$HOME/sno-diagnostics.XXXXXX")
date -u +'%Y-%m-%dT%H:%M:%SZ' > "$OUT/time.txt"
oc version --client > "$OUT/client-version.txt" 2>&1
oc get clusterversion -o yaml > "$OUT/clusterversion.yaml" 2>&1
oc get nodes -o wide > "$OUT/nodes.txt" 2>&1
oc get clusteroperators -o yaml > "$OUT/operators.yaml" 2>&1
oc describe clusteroperator authentication console ingress > "$OUT/operator-details.txt" 2>&1
oc get pods -n openshift-authentication -o wide > "$OUT/oauth-pods.txt" 2>&1
oc get pods -n openshift-ingress -o wide > "$OUT/ingress-pods.txt" 2>&1
oc get route -n openshift-authentication oauth-openshift -o yaml > "$OUT/oauth-route.yaml" 2>&1
oc logs -n openshift-authentication deployment/oauth-openshift \
  --all-containers=true --tail=200 > "$OUT/oauth.log" 2>&1
printf 'Private diagnostics: %s\n' "$OUT"
```

This collection intentionally continues after individual read failures so that
later evidence is still captured. Review each file for API errors and sensitive
information; directory creation does not imply that every command succeeded.
Do not publish a browser HAR, kubeconfig, installer-state archive, or full log
bundle without reviewing and redacting it.

Also record node-side `getent` results, the anonymous normal-DNS versus
`--resolve` health-request results, and a sanitized browser error/screenshot.
Use KVM boot output when no SSH/API connection is possible. Do not reset the
host just because an arbitrary time interval has elapsed.

## Before requesting another maintainer review

Record at least one successful manual run with an exact release and actual
console login. Test the helper separately or explicitly leave its result pending.
Check the edited YAML against the selected installer, verify links and Markdown
rendering, and retain the current non-production/support caveats.

Reconcile the author's intended OpenShift entitlement with the applicable
Red Hat terms; do not infer it solely from possession of a pull secret. Review
the contribution policy and decide with maintainers whether the external-helper
section belongs in the publication.

## Primary references

- [Source PR and discussion](https://github.com/hetzneronline/community-content/pull/1492)
- [Proposed revision](https://github.com/tomazb/hetzner-community-content/tree/sno-review-fixes)
- [Pinned helper implementation](https://github.com/tomazb/hetzner-sno-provision-host/blob/08615305502e22ebb1fd1f8bb9eb27281a681a27/hetzner-sno-prepare-pxe.sh)
- [Hetzner recursive resolvers](https://docs.hetzner.com/robot/dedicated-server/general-information/recursive-name-servers/)
- [Hetzner Robot firewall](https://docs.hetzner.com/robot/dedicated-server/firewall/)
- [Red Hat SNO requirements and DNS](https://docs.redhat.com/en/documentation/openshift_container_platform/4.22/html/installing_on_a_single_node/preparing-to-install-sno)
- [Red Hat installation validation](https://docs.redhat.com/en/documentation/openshift_container_platform/4.22/html/installation_overview/ocp-installation-overview)
- [Red Hat local storage and LVM Storage](https://docs.redhat.com/en/documentation/openshift_container_platform/4.22/html/storage/persistent-storage-using-local-storage)
- [Linux initramfs buffer format](https://docs.kernel.org/driver-api/early-userspace/buffer-format.html)
