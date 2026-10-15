#!/usr/bin/env python3
"""Offline checks for executable tutorial snippets; never provision a host.

Run with Python 3 and the standard library. Network, installation, and kexec
commands are replaced by fixtures. Real sha256sum and file operations run only
on temporary files. These tests do not validate an OpenShift installation.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = Path(os.environ.get("SNO_TUTORIAL", ROOT / "tutorials/setup-openshift-single-node/01.en.md"))


def bash_blocks():
    return re.findall(r"^```bash\n(.*?)^```", DOC.read_text(), re.M | re.S)


def snippet(needle):
    matches = [b for b in bash_blocks() if needle in b]
    if len(matches) != 1:
        raise AssertionError(f"Expected one Bash block containing {needle!r}, got {len(matches)}")
    return matches[0]


class TutorialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sno-test-")
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.fixtures = self.work / "fixtures"
        self.fixtures.mkdir()
        self.log = self.work / "commands.log"
        self.env = dict(os.environ, PATH=f"{self.bin}:/usr/bin:/bin", HOME=str(self.work),
                        TMPDIR=str(self.work), TEST_ROOT=str(self.work), LOG=str(self.log),
                        FIXTURES=str(self.fixtures), OCP_VERSION="4.22.1",
                        SERVER_IP="203.0.113.45", IP_WITH_PREFIX="203.0.113.45/26",
                        CLUSTER_NAME="sno", BASE_DOMAIN="example.com",
                        DNS1="185.12.64.1", DNS2="185.12.64.2")
        # Use the interpreter that launched these tests, even outside /usr/bin.
        self.stub("python3", f"#!/bin/sh\nexec '{sys.executable}' \"$@\"\n")
        self.stub("curl", r'''#!/bin/bash
args=("$@")
url='' out=''
for ((i=0; i<${#args[@]}; i++)); do
    case "${args[i]}" in
      https://*) url="${args[i]}" ;;
      --output|-o) out="${args[i+1]}" ;;
    esac
done
name="${url##*/}"
[[ "${FAIL_DOWNLOAD:-}" != "$name" ]] || exit 22
cp "$FIXTURES/$name" "${out:-$name}"
''')
        for command in ("tar", "install", "oc", "openshift-install", "sync"):
            self.stub(command, f'''#!/bin/bash
printf '%s\\n' '{command}' >> "$LOG"
[[ "${{FAIL_COMMAND:-}}" != '{command}' ]] || exit 23
''')
        self.stub("kexec", '''#!/bin/bash
printf 'kexec %s\\n' "$1" >> "$LOG"
if [[ "$1" == '-l' && "${FAIL_LOAD:-0}" == 1 ]]; then exit 24; fi
''')

    def stub(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o755)

    def run_block(self, needle, *, input_text="", **env):
        code = snippet(needle).replace("<ocp-version>", "4.22.1")
        code = code.replace("/root", str(self.work))
        return subprocess.run(["/bin/bash", "-c", code], cwd=self.work,
                              env=dict(self.env, **env), input=input_text,
                              text=True, capture_output=True, timeout=15)

    def commands(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def downloads(self):
        lines = []
        for name in ("openshift-client-linux.tar.gz", "openshift-install-linux.tar.gz"):
            data = f"fixture: {name}\n".encode()
            (self.fixtures / name).write_bytes(data)
            lines.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
        (self.fixtures / "sha256sum.txt").write_text("".join(lines))

    def test_checksum_mismatch_stops_before_extracting(self):
        self.downloads()
        (self.fixtures / "openshift-client-linux.tar.gz").write_text("tampered")
        run = self.run_block("BASE=https://mirror.openshift.com")
        self.assertNotEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertNotIn("tar", self.commands())
        self.assertNotIn("install", self.commands())

    def test_failed_download_stops_before_extracting(self):
        self.downloads()
        run = self.run_block("BASE=https://mirror.openshift.com",
                             FAIL_DOWNLOAD="openshift-install-linux.tar.gz")
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn("tar", self.commands())

    def test_missing_checksum_entry_is_rejected(self):
        self.downloads()
        manifest = self.fixtures / "sha256sum.txt"
        manifest.write_text(manifest.read_text().splitlines()[0] + "\n")
        run = self.run_block("BASE=https://mirror.openshift.com")
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn("tar", self.commands())

    def test_duplicate_checksum_entry_is_rejected(self):
        self.downloads()
        manifest = self.fixtures / "sha256sum.txt"
        manifest.write_text(manifest.read_text() * 2)
        run = self.run_block("BASE=https://mirror.openshift.com")
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn("tar", self.commands())

    def test_valid_checksums_allow_both_archives(self):
        self.downloads()
        run = self.run_block("BASE=https://mirror.openshift.com")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(self.commands().count("tar"), 2)
        self.assertIn("install", self.commands())

    def test_archive_failure_stops_before_installing(self):
        self.downloads()
        run = self.run_block("BASE=https://mirror.openshift.com", FAIL_COMMAND="tar")
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn("install", self.commands())

    def test_invalid_release_is_rejected_before_installing(self):
        run = self.run_block("BASE=https://mirror.openshift.com", OCP_VERSION="latest")
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn("install", self.commands())

    def test_failed_kernel_load_never_executes(self):
        run = self.run_block("kexec -l", input_text="BOOT\n", FAIL_LOAD="1")
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn("kexec -e", self.commands())

    def test_boot_requires_explicit_confirmation(self):
        run = self.run_block("kexec -l", input_text="no\n")
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn("kexec -e", self.commands())
        self.assertIn("kexec -u", self.commands())

    def test_confirmed_successful_load_can_execute(self):
        run = self.run_block("kexec -l", input_text="BOOT\n")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual([c for c in self.commands() if c.startswith("kexec")],
                         ["kexec -l", "kexec -e"])

    def test_combined_initrd_all_alignment_residues(self):
        for size in range(1, 9):
            with self.subTest(size=size):
                initrd = b"I" * size
                rootfs = b"ROOTFS"
                (self.work / "agent.x86_64-initrd.img").write_bytes(initrd)
                (self.work / "agent.x86_64-rootfs.img").write_bytes(rootfs)
                run = self.run_block("INITRD_SIZE=")
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                data = (self.work / "agent.x86_64-combinedinitrd.img").read_bytes()
                pad = 4 + ((4 - size % 4) % 4)
                self.assertEqual(data, initrd + b"\0" * pad + rootfs)
                self.assertEqual((size + pad) % 4, 0)

    def test_missing_rootfs_does_not_publish_partial_initrd(self):
        (self.work / "agent.x86_64-initrd.img").write_bytes(b"INITRD")
        run = self.run_block("INITRD_SIZE=")
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse((self.work / "agent.x86_64-combinedinitrd.img").exists())

    def test_network_calculation(self):
        for value, expected in (("203.0.113.45/26", "203.0.113.0/26"),
                                ("203.0.113.201/27", "203.0.113.192/27")):
            with self.subTest(value=value):
                run = self.run_block("ipaddress.ip_interface", IP_WITH_PREFIX=value)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertIn(expected, run.stdout)

    def test_network_rejects_invalid_or_ipv6_input(self):
        for value in ("not-an-address", "2001:db8::1/64"):
            with self.subTest(value=value):
                run = self.run_block("ipaddress.ip_interface", IP_WITH_PREFIX=value)
                self.assertNotEqual(run.returncode, 0)

    def dns_fixture(self):
        self.stub("dig", r'''#!/bin/bash
args=("$@")
host="${args[${#args[@]}-2]}"
kind="${args[${#args[@]}-1]}"
case="${DNS_CASE:-good}"
[[ "$case" != transport ]] || exit 9
if [[ "$kind" == AAAA ]]; then
    if [[ "$case" == ipv6 ]]; then printf '%s. 60 IN AAAA 2001:db8::1\n' "$host"; fi
elif [[ "$case" != missing ]]; then
    ip=203.0.113.45
    if [[ "$case" == multiple ]]; then printf '%s. 60 IN A 192.0.2.99\n' "$host"; fi
    if [[ "$case" == secondary && "$*" == *'@185.12.64.2'* ]]; then ip=192.0.2.99; fi
    [[ "$case" != wrong ]] || ip=192.0.2.99
    printf '%s. 60 IN A %s\n' "$host" "$ip"
fi
''')

    def test_dns_preflight_passes_consistent_ipv4_answers(self):
        self.dns_fixture()
        run = self.run_block('for dns in "$DNS1" "$DNS2"')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_dns_preflight_rejects_bad_answers(self):
        self.dns_fixture()
        for case in ("missing", "wrong", "transport", "ipv6", "multiple", "secondary"):
            with self.subTest(case=case):
                run = self.run_block('for dns in "$DNS1" "$DNS2"', DNS_CASE=case)
                self.assertNotEqual(run.returncode, 0, run.stdout + run.stderr)

    def health_fixture(self, bad=None, missing=False):
        items = []
        for name in ("authentication", "console", "ingress"):
            conditions = [{"type": t, "status": s} for t, s in
                          (("Available", "True"), ("Progressing", "False"), ("Degraded", "False"))]
            if name == "authentication":
                if bad: conditions[-1]["status"] = bad
                if missing: conditions.pop()
            items.append({"metadata": {"name": name}, "status": {"conditions": conditions}})
        path = self.work / "operators.json"
        path.write_text(json.dumps({"items": items}))
        self.stub("oc", f'#!/bin/sh\ncat "{path}"\n')
        return path

    def test_readiness_accepts_healthy_operators(self):
        self.health_fixture()
        run = self.run_block("required_conditions =")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_readiness_rejects_degraded_unknown_or_missing_conditions(self):
        for status, missing in (("True", False), ("Unknown", False), (None, True)):
            with self.subTest(status=status, missing=missing):
                self.health_fixture(status, missing)
                run = self.run_block("required_conditions =")
                self.assertNotEqual(run.returncode, 0)

    def test_readiness_rejects_empty_operator_list(self):
        path = self.health_fixture()
        path.write_text('{"items": []}')
        run = self.run_block("required_conditions =")
        self.assertNotEqual(run.returncode, 0)

    def test_readiness_rejects_missing_critical_operator(self):
        path = self.health_fixture()
        data = json.loads(path.read_text())
        data["items"].pop()
        path.write_text(json.dumps(data))
        run = self.run_block("required_conditions =")
        self.assertNotEqual(run.returncode, 0)

    def test_empty_download_is_rejected(self):
        self.downloads()
        (self.fixtures / "openshift-client-linux.tar.gz").write_bytes(b"")
        run = self.run_block("BASE=https://mirror.openshift.com")
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn("tar", self.commands())

    def test_helper_paths_and_arguments_are_consistent(self):
        helper_dir = self.work / "hetzner-sno-provision-host"
        helper_dir.mkdir()
        helper = helper_dir / "hetzner-sno-prepare-pxe.sh"
        # Preserve the upstream INSTALL_DIR-within-WORKDIR constraint in this
        # boundary fixture. This does not execute the external helper itself.
        helper.write_text(r'''#!/bin/bash
set -eu
[[ "$INSTALL_DIR" == "$WORKDIR/"* ]] || exit 42
printf 'helper:%s|%s|%s\n' "$WORKDIR" "$INSTALL_DIR" "$*" >> "$LOG"
mkdir -p "$INSTALL_DIR"
printf 'fixture\n' > "$WORKDIR/install-config.yaml.bak"
printf 'fixture\n' > "$WORKDIR/agent-config.yaml.bak"
''')
        helper.chmod(0o755)
        code = snippet("PREPARE_ARGS=(") + "\n" + snippet("--interactive")
        code = code.replace("/root", str(self.work))
        env = dict(self.env, DISK_SERIAL="TEST-SERIAL", NODE_HOSTNAME="sno.example.com",
                   INTERFACE="enp41s0", GATEWAY="203.0.113.1")
        run = subprocess.run(["/bin/bash", "-c", code], cwd=self.work, env=env,
                             capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        calls = [c.split("|", 2)[2] for c in self.commands() if c.startswith("helper:")]
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].replace("--dry-run ", "", 1),
                         calls[1].replace("--interactive ", "", 1))
        for flag in ("--hostname", "--ssh-public-key-file", "--dns-server", "--ip-family v4"):
            self.assertIn(flag, calls[0])

    def test_common_kexec_dependency_precedes_helper_path(self):
        doc = DOC.read_text()
        self.assertLess(doc.index("apt-get install -y ca-certificates curl dnsutils git python3 kexec-tools"),
                        doc.index("<details>"))

    def test_all_bash_blocks_parse_after_placeholder_substitution(self):
        self.assertGreater(len(bash_blocks()), 10)
        for index, block in enumerate(bash_blocks(), 1):
            code = re.sub(r"<[a-z][a-z0-9-]*>", "EXAMPLE", block)
            run = subprocess.run(["/bin/bash", "-n"], input=code, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, f"Block {index}: {run.stderr}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
