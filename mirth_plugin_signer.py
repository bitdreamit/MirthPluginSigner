"""
================================================================================
  Mirth Connect Plugin Signer — Professional GUI Tool
  Version 2.0.0 | Python 3.8+
================================================================================

PURPOSE
    Signs, packages, and deploys Mirth Connect / BridgeLink plugin JARs and WARs
    using a full graphical interface. No separate .bat files required — this
    Python script IS the tool.

STRUCTURE  (all paths relative to this .py file)
    mirth_plugin_signer.py      ← this file, place anywhere
    config/
        config.json             ← saved settings (auto-created on first run)
    plugins/
        <plugin-name>/          ← one subfolder per plugin
            *.jar / *.war       ← source files
            plugin.xml          ← optional Mirth descriptor
            plugin-extension.xml
    sign/
        <plugin-name>/          ← signed JARs/WARs written here
            <plugin-name>.zip   ← deployment package
    certificates/
        self-signed/            ← auto-generated .jks / .cer / .p12
        commercial/             ← place purchased .jks or .p12 here

REQUIREMENTS
    - Python 3.8+ (standard library only — no pip install needed)
    - Java Development Kit (JDK) — provides keytool + jarsigner
    - tkinter (bundled with standard CPython on Windows/macOS/Linux)

USAGE
    python mirth_plugin_signer.py

WORKFLOW
    1. Settings tab  → configure Mirth path, certificate details, passwords
    2. Plugins tab   → check which plugin folders to process
    3. Certificates  → generate self-signed cert OR verify commercial cert
    4. Sign tab      → strip old sigs, sign all JARs/WARs, verify
    5. Package tab   → create deployment ZIP with optional install.bat
    6. Deploy tab    → copy to Mirth extensions, import cert, write policy
    7. Logs tab      → real-time output of every operation

NOTES
    • All signing is done on a COPY inside sign/<plugin>/ — source files
      are never modified.
    • Existing signatures (.SF/.RSA/.DSA/.EC) are stripped before re-signing
      to avoid "multiple signer blocks" errors.
    • The security policy (custom.policy) is scoped per-plugin — no global
      AllPermission grant.
    • mirth.properties is backed up before any modification.
    • Duplicate java.security.policy entries are prevented automatically.

COMMERCIAL CERTIFICATE
    Place your purchased .jks or .p12 file in  certificates/commercial/
    then select "Commercial" in the Certificates tab and fill in alias +
    password. The tool will use it instead of the self-signed cert.

SUPPORTED TARGETS
    - Mirth Connect  (extensions/ folder layout)
    - BridgeLink     (same extensions/ layout, configurable path)

CHANGELOG
    2.0.0  Full GUI rewrite; multi-plugin selection; ZIP packaging;
           config persistence; threaded operations; real-time logs.
    1.0.0  Initial batch-file toolkit.
================================================================================
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import json
import os
import sys
import shutil
import subprocess
import threading
import zipfile
import datetime
import pathlib
import queue


# ─── Constants ────────────────────────────────────────────────────────────────

APP_TITLE   = "Mirth Connect Plugin Signer"
APP_VERSION = "2.0.0"

BASE_DIR    = pathlib.Path(sys.argv[0]).resolve().parent
CONFIG_DIR  = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "config.json"
PLUGINS_DIR = BASE_DIR / "plugins"
SIGN_DIR    = BASE_DIR / "sign"
CERTS_DIR   = BASE_DIR / "certificates"

TSA_SERVERS = {
    "DigiCert":   "http://timestamp.digicert.com",
    "Sectigo":    "http://timestamp.sectigo.com",
    "GlobalSign": "http://timestamp.globalsign.com/scripts/timstamp.dll",
    "None":       "",
}

DEFAULT_CONFIG = {
    # Mirth / BridgeLink
    "mirth_dir":        "C:\\Program Files\\Mirth Connect",
    "target_type":      "Mirth Connect",   # or "BridgeLink"

    # Certificate — identity
    "cert_alias":       "mirth-plugin-signer",
    "cert_cn":          "Mirth Plugin Signer",
    "cert_org":         "My Organisation",
    "cert_ou":          "Development",
    "cert_city":        "Rangpur",
    "cert_state":       "Rangpur",
    "cert_country":     "BD",
    "cert_validity":    "3650",

    # Certificate — crypto
    "cert_type":        "self-signed",   # "self-signed" | "commercial"
    "key_alg":          "RSA",
    "key_size":         "4096",
    "sig_alg":          "SHA256withRSA",
    "tsa_server":       "http://timestamp.digicert.com",

    # Certificate — commercial path (only used when cert_type == "commercial")
    "commercial_path":  "",
    "commercial_alias": "1",

    # Passwords (stored locally — protect this config folder)
    "store_pass":       "",
    "key_pass":         "",

    # Signing options
    "opt_strip_sigs":   True,   # remove old .SF/.RSA before re-signing
    "opt_verify":       True,   # verify every JAR after signing
    "opt_sign_war":     True,   # also sign .war files

    # Output options
    "opt_create_zip":       True,
    "opt_include_install":  True,   # embed install.bat in ZIP

    # Deploy options
    "opt_auto_deploy":      False,
    "opt_import_cert":      True,
    "opt_write_policy":     True,
    "opt_dedup_props":      True,
    "opt_backup_props":     True,
    "opt_restart_mirth":    False,

    # Version for ZIP filename
    "plugin_version":       "1.0.0",
}


# ─── Palette ──────────────────────────────────────────────────────────────────

PAL = {
    "bg":           "#F7F7F7",
    "bg2":          "#EFEFEF",
    "bg3":          "#E4E4E4",
    "sidebar":      "#1E2A3A",
    "sidebar_sel":  "#2D4A6A",
    "sidebar_txt":  "#C8D8E8",
    "sidebar_sel_txt": "#FFFFFF",
    "accent":       "#185FA5",
    "accent_h":     "#0C447C",
    "text":         "#1A1A1A",
    "text2":        "#555555",
    "text3":        "#888888",
    "border":       "#D8D8D8",
    "ok":           "#2E7D32",
    "warn":         "#E65100",
    "err":          "#B71C1C",
    "ok_bg":        "#E8F5E9",
    "warn_bg":      "#FFF3E0",
    "err_bg":       "#FFEBEE",
    "log_bg":       "#0F1923",
    "log_fg":       "#C8D8E8",
    "log_ok":       "#4CAF50",
    "log_warn":     "#FFA726",
    "log_err":      "#EF5350",
    "log_info":     "#29B6F6",
    "log_step":     "#CE93D8",
    "white":        "#FFFFFF",
}

FONT_UI   = ("Segoe UI", 10)
FONT_SM   = ("Segoe UI", 9)
FONT_LG   = ("Segoe UI", 12)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_MONO = ("Consolas", 10) if sys.platform == "win32" else ("Menlo", 10)


# ─── Config Manager ───────────────────────────────────────────────────────────

class ConfigManager:
    """
    Loads and saves application settings to config/config.json.
    Falls back to DEFAULT_CONFIG for any missing key.
    """
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._data = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data.update(saved)
            except Exception:
                pass  # corrupt config → use defaults

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            print(f"[WARN] Could not save config: {e}")

    def get(self, key, default=None):
        return self._data.get(key, DEFAULT_CONFIG.get(key, default))

    def set(self, key, value):
        self._data[key] = value

    def all(self):
        return dict(self._data)


# ─── Signer Engine ────────────────────────────────────────────────────────────

class SignerEngine:
    """
    Core signing logic. All heavy operations run here (called from threads).
    Emits log messages via the provided log_callback(level, message).

    Levels: "step" | "info" | "ok" | "warn" | "err"
    """

    def __init__(self, config: ConfigManager, log_callback):
        self.cfg = config
        self.log = log_callback

    # ── helpers ───────────────────────────────────────────────────────────────

    def _run(self, cmd, cwd=None):
        """Run a subprocess; return (returncode, stdout+stderr combined)."""
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=cwd,
                text=True,
            )
            return result.returncode, result.stdout
        except FileNotFoundError:
            return 1, f"Command not found: {cmd[0]}"

    def _find_tool(self, name):
        """Locate keytool / jarsigner — try JAVA_HOME first, then PATH."""
        java_home = os.environ.get("JAVA_HOME", "")
        if java_home:
            candidate = pathlib.Path(java_home) / "bin" / name
            if sys.platform == "win32":
                candidate = candidate.with_suffix(".exe")
            if candidate.exists():
                return str(candidate)
        # fall back to PATH
        found = shutil.which(name)
        if found:
            return found
        raise FileNotFoundError(
            f"'{name}' not found. Install a JDK and add its bin/ to PATH "
            f"(or set JAVA_HOME)."
        )

    def _keystore_path(self):
        if self.cfg.get("cert_type") == "commercial":
            p = self.cfg.get("commercial_path", "")
            if not p:
                raise ValueError("Commercial certificate path is not set.")
            return pathlib.Path(p)
        return CERTS_DIR / "self-signed" / f"{self.cfg.get('cert_alias')}.jks"

    def _cert_alias(self):
        if self.cfg.get("cert_type") == "commercial":
            return self.cfg.get("commercial_alias", "1")
        return self.cfg.get("cert_alias")

    def _cer_path(self):
        alias = self.cfg.get("cert_alias")
        return CERTS_DIR / "self-signed" / f"{alias}.cer"

    def _strip_signatures(self, jar_path: pathlib.Path):
        """Remove META-INF .SF/.RSA/.DSA/.EC entries from a JAR/WAR in-place."""
        try:
            import zipfile as zf
            tmp = jar_path.with_suffix(".tmp")
            with zf.ZipFile(jar_path, "r") as zin:
                with zf.ZipFile(tmp, "w", compression=zf.ZIP_DEFLATED) as zout:
                    for item in zin.infolist():
                        name_upper = item.filename.upper()
                        # Skip old signature files
                        if (name_upper.startswith("META-INF/") and
                                name_upper.endswith((".SF", ".RSA", ".DSA", ".EC"))):
                            continue
                        zout.writestr(item, zin.read(item.filename))
            jar_path.unlink()
            tmp.rename(jar_path)
        except Exception as e:
            self.log("warn", f"  Strip sigs failed for {jar_path.name}: {e}")

    # ── public operations ─────────────────────────────────────────────────────

    def check_java(self):
        """Verify keytool and jarsigner are accessible. Returns True/False."""
        ok = True
        for tool in ("keytool", "jarsigner"):
            try:
                p = self._find_tool(tool)
                self.log("ok", f"  Found {tool}: {p}")
            except FileNotFoundError as e:
                self.log("err", f"  {e}")
                ok = False
        return ok

    def generate_certificate(self):
        """
        Generate a self-signed certificate (.jks + .cer + .p12).
        Skips if keystore already exists (user must delete manually to regenerate).
        """
        self.log("step", "─── Generate Certificate ───────────────────────────")

        ks = self._keystore_path()
        cer = self._cer_path()
        alias = self.cfg.get("cert_alias")
        sp = self.cfg.get("store_pass")
        kp = self.cfg.get("key_pass")

        if not sp or not kp:
            self.log("err", "  Store password and key password must not be empty.")
            return False

        ks.parent.mkdir(parents=True, exist_ok=True)

        if ks.exists():
            self.log("info", f"  Keystore exists — reusing: {ks}")
            self.log("info", "  Delete it to regenerate a fresh certificate.")
        else:
            self.log("info", f"  Generating {self.cfg.get('key_size')}-bit "
                             f"{self.cfg.get('key_alg')} certificate...")
            dname = (
                f"CN={self.cfg.get('cert_cn')}, "
                f"OU={self.cfg.get('cert_ou')}, "
                f"O={self.cfg.get('cert_org')}, "
                f"L={self.cfg.get('cert_city')}, "
                f"ST={self.cfg.get('cert_state')}, "
                f"C={self.cfg.get('cert_country')}"
            )
            cmd = [
                self._find_tool("keytool"),
                "-genkeypair",
                "-alias", alias,
                "-keystore", str(ks),
                "-storepass", sp,
                "-keypass", kp,
                "-keyalg", self.cfg.get("key_alg"),
                "-keysize", self.cfg.get("key_size"),
                "-sigalg", self.cfg.get("sig_alg"),
                "-validity", self.cfg.get("cert_validity"),
                "-dname", dname,
            ]
            rc, out = self._run(cmd)
            if rc != 0:
                self.log("err", f"  Certificate generation failed:\n{out}")
                return False
            self.log("ok", f"  Keystore created: {ks}")

        # Export .cer
        if not cer.exists():
            self.log("info", "  Exporting public certificate (.cer)...")
            cmd = [
                self._find_tool("keytool"),
                "-exportcert",
                "-alias", alias,
                "-keystore", str(ks),
                "-storepass", sp,
                "-file", str(cer),
            ]
            rc, out = self._run(cmd)
            if rc != 0:
                self.log("warn", f"  .cer export warning: {out}")
            else:
                self.log("ok", f"  Certificate: {cer}")

        # Export .p12
        p12 = ks.with_suffix(".p12")
        if not p12.exists():
            self.log("info", "  Exporting PKCS12 (.p12)...")
            cmd = [
                self._find_tool("keytool"),
                "-importkeystore",
                "-srckeystore", str(ks),
                "-destkeystore", str(p12),
                "-srcstoretype", "JKS",
                "-deststoretype", "PKCS12",
                "-srcstorepass", sp,
                "-deststorepass", sp,
                "-srckeypass", kp,
                "-destkeypass", kp,
                "-alias", alias,
                "-noprompt",
            ]
            rc, out = self._run(cmd)
            if rc != 0:
                self.log("warn", f"  .p12 export warning (non-fatal): {out}")
            else:
                self.log("ok", f"  PKCS12: {p12}")

        self.log("ok", "  Certificate step complete.")
        return True

    def sign_plugins(self, plugin_names: list):
        """
        Sign all JARs (and optionally WARs) for each named plugin.
        Files are copied to sign/<plugin>/ before signing — source is untouched.

        Returns dict { plugin_name: {"signed": n, "failed": n, "total": n} }
        """
        self.log("step", "─── Sign Plugins ───────────────────────────────────")

        results = {}
        ks = self._keystore_path()
        alias = self._cert_alias()
        sp = self.cfg.get("store_pass")
        kp = self.cfg.get("key_pass")
        sig_alg = self.cfg.get("sig_alg")
        tsa = self.cfg.get("tsa_server", "")
        do_strip = self.cfg.get("opt_strip_sigs", True)
        do_verify = self.cfg.get("opt_verify", True)
        do_war = self.cfg.get("opt_sign_war", True)

        if not ks.exists():
            self.log("err", f"  Keystore not found: {ks}")
            self.log("err", "  Generate a certificate first (Certificates tab).")
            return {}

        jarsigner = self._find_tool("jarsigner")
        SIGN_DIR.mkdir(parents=True, exist_ok=True)

        for pname in plugin_names:
            src_dir = PLUGINS_DIR / pname
            out_dir = SIGN_DIR / pname
            out_dir.mkdir(parents=True, exist_ok=True)

            self.log("step", f"\n  Plugin: {pname}")

            patterns = ["*.jar"] + (["*.war"] if do_war else [])
            sources = []
            for pat in patterns:
                sources.extend(sorted(src_dir.glob(pat)))

            if not sources:
                self.log("warn", f"  No JAR/WAR files found in {src_dir}")
                results[pname] = {"signed": 0, "failed": 0, "total": 0}
                continue

            signed = failed = 0
            for src in sources:
                dest = out_dir / src.name
                self.log("info", f"  Processing: {src.name}")

                # Copy source → output (never touch original)
                shutil.copy2(src, dest)

                # Strip old signatures
                if do_strip:
                    self._strip_signatures(dest)

                # Build jarsigner command
                cmd = [
                    jarsigner,
                    "-keystore", str(ks),
                    "-storepass", sp,
                    "-keypass", kp,
                    "-sigAlg", sig_alg,
                ]
                if tsa:
                    cmd += ["-tsa", tsa]
                cmd += [str(dest), alias]

                rc, out = self._run(cmd)
                if rc != 0:
                    self.log("err", f"  [FAIL] {src.name}")
                    if out.strip():
                        self.log("err", f"         {out.strip()[:200]}")
                    failed += 1
                    continue

                # Verify
                if do_verify:
                    rc2, out2 = self._run([jarsigner, "-verify", str(dest)])
                    if rc2 != 0:
                        self.log("warn", f"  [WARN] {src.name} — signed but verify failed")
                        failed += 1
                    else:
                        self.log("ok", f"  [ OK ] {src.name}")
                        signed += 1
                else:
                    self.log("ok", f"  [ OK ] {src.name}")
                    signed += 1

            # Copy descriptors
            for desc in ("plugin.xml", "plugin-extension.xml", "extension.xml"):
                src_desc = src_dir / desc
                if src_desc.exists():
                    shutil.copy2(src_desc, out_dir / desc)
                    self.log("info", f"  Copied descriptor: {desc}")

            results[pname] = {"signed": signed, "failed": failed, "total": len(sources)}
            self.log("ok" if failed == 0 else "warn",
                     f"  Result: {signed}/{len(sources)} signed"
                     + (f", {failed} failed" if failed else ""))

        return results

    def create_packages(self, plugin_names: list):
        """
        Create a deployment ZIP for each plugin inside sign/<plugin>/.
        Optionally embeds an install.bat.
        """
        self.log("step", "─── Create Packages ────────────────────────────────")
        version = self.cfg.get("plugin_version", "1.0.0")
        mirth_dir = self.cfg.get("mirth_dir")
        include_install = self.cfg.get("opt_include_install", True)

        for pname in plugin_names:
            out_dir = SIGN_DIR / pname
            if not out_dir.exists():
                self.log("warn", f"  {pname}: no signed output folder — run Sign first.")
                continue

            zip_path = out_dir / f"{pname}-v{version}.zip"
            if zip_path.exists():
                zip_path.unlink()

            self.log("info", f"  Packaging: {pname} → {zip_path.name}")

            # Gather files to zip
            files_to_add = (
                list(out_dir.glob("*.jar")) +
                list(out_dir.glob("*.war")) +
                [f for f in (
                    out_dir / "plugin.xml",
                    out_dir / "plugin-extension.xml",
                    out_dir / "extension.xml",
                ) if f.exists()]
            )

            # Include certificate
            cer = self._cer_path()
            if cer.exists():
                files_to_add.append(cer)

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in files_to_add:
                    zf.write(f, f"extensions/{pname}/{f.name}")
                if include_install:
                    install_script = self._make_install_bat(pname, version, mirth_dir)
                    zf.writestr("install.bat", install_script)
                    zf.writestr("README.txt", self._make_readme(pname, version))

            self.log("ok", f"  Package: {zip_path}")

        self.log("ok", "  Packaging complete.")

    def _make_install_bat(self, pname, version, mirth_dir):
        """Generate a self-contained install.bat for end users."""
        lines = [
            "@echo off",
            f"title Install {pname} v{version}",
            "net session >nul 2>&1",
            "if %errorLevel% neq 0 ("
            "  echo Run as Administrator & pause & exit /b 1 )",
            f'set "MIRTH_DIR={mirth_dir}"',
            f'set "EXT_DIR=%MIRTH_DIR%\\extensions\\{pname}"',
            'mkdir "%EXT_DIR%" 2>nul',
            f'xcopy /y /q "extensions\\{pname}\\*" "%EXT_DIR%\\"',
            f'if exist "extensions\\{pname}\\*.cer" (',
            f'  keytool -importcert -file "extensions\\{pname}\\{pname}.cer"'
            f' -keystore "%MIRTH_DIR%\\jre\\lib\\security\\cacerts"'
            f' -alias "{pname}" -storepass changeit -trustcacerts -noprompt >nul 2>&1',
            ")",
            "echo.",
            f"echo {pname} v{version} installed.",
            "echo Restart Mirth Connect to activate the plugin.",
            "echo.",
            "pause",
        ]
        return "\r\n".join(lines)

    def _make_readme(self, pname, version):
        return (
            f"{pname} v{version}\n"
            f"{'='*40}\n\n"
            f"Installation:\n"
            f"  1. Run install.bat as Administrator\n"
            f"  2. Restart Mirth Connect\n\n"
            f"Manual installation:\n"
            f"  Copy extensions/{pname}/*.jar to Mirth/extensions/{pname}/\n"
            f"  Restart Mirth Connect\n\n"
            f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        )

    def deploy_plugins(self, plugin_names: list):
        """
        Copy signed JARs/WARs to Mirth extensions folder.
        Optionally import certificate, write policy, update mirth.properties.
        """
        self.log("step", "─── Deploy to Mirth ────────────────────────────────")

        mirth_dir = pathlib.Path(self.cfg.get("mirth_dir"))
        if not mirth_dir.exists():
            self.log("err", f"  Mirth directory not found: {mirth_dir}")
            self.log("err", "  Update the Mirth path in Settings.")
            return False

        for pname in plugin_names:
            out_dir = SIGN_DIR / pname
            ext_dir = mirth_dir / "extensions" / pname
            ext_dir.mkdir(parents=True, exist_ok=True)

            self.log("info", f"  Deploying: {pname} → {ext_dir}")

            count = 0
            for pat in ("*.jar", "*.war"):
                for f in out_dir.glob(pat):
                    shutil.copy2(f, ext_dir / f.name)
                    count += 1
            for desc in ("plugin.xml", "plugin-extension.xml", "extension.xml"):
                src = out_dir / desc
                if src.exists():
                    shutil.copy2(src, ext_dir / desc)

            self.log("ok", f"  Deployed {count} file(s) to {ext_dir}")

        # Import certificate to Mirth JRE
        if self.cfg.get("opt_import_cert"):
            self._import_cert_to_mirth(mirth_dir)

        # Write security policy
        if self.cfg.get("opt_write_policy"):
            self._write_security_policy(mirth_dir, plugin_names)

        # Restart
        if self.cfg.get("opt_restart_mirth"):
            self._restart_mirth()

        return True

    def _import_cert_to_mirth(self, mirth_dir: pathlib.Path):
        """Import .cer into Mirth's bundled JRE cacerts."""
        self.log("info", "  Importing certificate to Mirth JRE truststore...")

        cer = self._cer_path()
        if not cer.exists():
            self.log("warn", "  Certificate file (.cer) not found — skipping import.")
            return

        # Detect which JRE Mirth bundles
        mirth_jre = None
        for subdir in ("jre", "jre17", "jre21", "jre11"):
            candidate = mirth_dir / subdir
            if (candidate / "bin").exists():
                mirth_jre = candidate
                break
        if not mirth_jre:
            java_home = os.environ.get("JAVA_HOME")
            if java_home:
                mirth_jre = pathlib.Path(java_home)

        if not mirth_jre:
            self.log("warn", "  Could not locate Mirth JRE — skipping cert import.")
            return

        truststore = mirth_jre / "lib" / "security" / "cacerts"
        kt = str(mirth_jre / "bin" / "keytool")
        if sys.platform == "win32":
            kt += ".exe"
        if not pathlib.Path(kt).exists():
            kt = shutil.which("keytool") or "keytool"

        alias = self.cfg.get("cert_alias")

        # Check if already imported
        rc, _ = self._run([kt, "-list", "-alias", alias,
                           "-keystore", str(truststore), "-storepass", "changeit"])
        if rc == 0:
            self.log("info", "  Certificate already in truststore — skipping.")
            return

        cmd = [
            kt, "-importcert",
            "-file", str(cer),
            "-keystore", str(truststore),
            "-alias", alias,
            "-storepass", "changeit",
            "-trustcacerts", "-noprompt",
        ]
        rc, out = self._run(cmd)
        if rc == 0:
            self.log("ok", f"  Certificate imported to {mirth_jre}")
        else:
            self.log("warn", f"  Import failed (may need admin): {out.strip()[:150]}")

    def _write_security_policy(self, mirth_dir: pathlib.Path, plugin_names: list):
        """Write custom.policy and update mirth.properties."""
        self.log("info", "  Writing security policy...")

        conf_dir = mirth_dir / "conf"
        policy_file = conf_dir / "custom.policy"
        props_file = conf_dir / "mirth.properties"

        # Backup mirth.properties
        if self.cfg.get("opt_backup_props") and props_file.exists():
            backup = props_file.with_suffix(".properties.backup")
            if not backup.exists():
                shutil.copy2(props_file, backup)
                self.log("ok", f"  Backup: {backup.name}")

        # Build policy content — scoped per plugin (not global AllPermission)
        mirth_str = str(mirth_dir).replace("\\", "/").replace(":", "")
        lines = [
            f"// Mirth Connect Plugin Security Policy",
            f"// Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"// Plugins: {', '.join(plugin_names)}",
            "",
        ]
        for pname in plugin_names:
            lines += [
                f'grant codeBase "file:/{mirth_str}/extensions/{pname}/-" {{',
                f'    permission java.security.AllPermission;',
                f'}};',
                "",
            ]

        try:
            policy_file.write_text("\n".join(lines), encoding="utf-8")
            self.log("ok", f"  Policy: {policy_file}")
        except PermissionError:
            self.log("err", "  Cannot write policy file — run as Administrator.")
            return

        # Update mirth.properties
        policy_uri = f"file:/{mirth_str}/conf/custom.policy"
        if props_file.exists():
            content = props_file.read_text(encoding="utf-8", errors="replace")
            if "java.security.policy" in content:
                if self.cfg.get("opt_dedup_props"):
                    self.log("info", "  java.security.policy already in mirth.properties — skipped.")
                    return
            try:
                with open(props_file, "a", encoding="utf-8") as f:
                    f.write(f"\n# Plugin security policy (mirth-plugin-signer)\n")
                    f.write(f"java.security.policy={policy_uri}\n")
                self.log("ok", "  mirth.properties updated.")
            except PermissionError:
                self.log("err", "  Cannot update mirth.properties — run as Administrator.")

    def _restart_mirth(self):
        """Restart the Mirth Connect Windows service."""
        self.log("info", "  Restarting Mirth Connect service...")
        for action in ("stop", "start"):
            rc, out = self._run(["net", action, "Mirth Connect Service"])
            if rc == 0:
                self.log("ok", f"  net {action} OK")
            else:
                self.log("warn", f"  net {action} failed: {out.strip()[:100]}")

    def verify_signed(self, plugin_names: list):
        """Run jarsigner -verify on all signed files."""
        self.log("step", "─── Verify Signatures ──────────────────────────────")
        jarsigner = self._find_tool("jarsigner")
        for pname in plugin_names:
            out_dir = SIGN_DIR / pname
            for f in sorted(out_dir.glob("*.jar")) + sorted(out_dir.glob("*.war")):
                rc, out = self._run([jarsigner, "-verify", "-verbose", "-certs", str(f)])
                status = "ok" if rc == 0 else "err"
                self.log(status, f"  [{' OK ' if rc==0 else 'FAIL'}] {f.name}")


# ─── App (GUI) ────────────────────────────────────────────────────────────────

class MirthSignerApp(tk.Tk):
    """
    Main application window.

    Layout:
        Left sidebar  — navigation buttons
        Right content — tab frames (Dashboard, Plugins, Certificates,
                        Sign, Package, Deploy, Settings, Logs)
    """

    def __init__(self):
        super().__init__()
        self.cfg = ConfigManager()
        self.log_queue = queue.Queue()
        self.engine = SignerEngine(self.cfg, self._enqueue_log)

        self.title(f"{APP_TITLE}  v{APP_VERSION}")
        self.configure(bg=PAL["bg"])
        self.geometry("1040x720")
        self.minsize(900, 620)

        self._plugin_vars = {}   # pname → BooleanVar
        self._current_panel = None
        self._panels = {}
        self._nav_buttons = {}

        self._build_ui()
        self._refresh_plugins()
        self._show_panel("dashboard")
        self._poll_log_queue()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Outer frame
        outer = tk.Frame(self, bg=PAL["bg"])
        outer.pack(fill="both", expand=True)

        # Sidebar
        self.sidebar = tk.Frame(outer, bg=PAL["sidebar"], width=190)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self._build_sidebar()

        # Content area
        content_wrap = tk.Frame(outer, bg=PAL["bg"])
        content_wrap.pack(side="left", fill="both", expand=True)

        # Title bar
        title_bar = tk.Frame(content_wrap, bg=PAL["bg"], pady=0)
        title_bar.pack(fill="x", padx=0)
        self._page_title_var = tk.StringVar(value="Dashboard")
        tk.Label(title_bar, textvariable=self._page_title_var,
                 font=("Segoe UI", 14, "bold"), bg=PAL["bg"],
                 fg=PAL["text"], anchor="w", padx=20, pady=14
                 ).pack(side="left")
        self._page_sub_var = tk.StringVar(value="")
        tk.Label(title_bar, textvariable=self._page_sub_var,
                 font=FONT_SM, bg=PAL["bg"], fg=PAL["text3"], anchor="w"
                 ).pack(side="left", padx=(0,0), pady=14)

        sep = tk.Frame(content_wrap, bg=PAL["border"], height=1)
        sep.pack(fill="x")

        # Panel container
        self.panel_frame = tk.Frame(content_wrap, bg=PAL["bg"])
        self.panel_frame.pack(fill="both", expand=True)

        # Build all panels
        self._build_panel_dashboard()
        self._build_panel_plugins()
        self._build_panel_certificates()
        self._build_panel_sign()
        self._build_panel_package()
        self._build_panel_deploy()
        self._build_panel_settings()
        self._build_panel_logs()

    def _build_sidebar(self):
        # App logo area
        logo = tk.Frame(self.sidebar, bg=PAL["sidebar"], pady=18)
        logo.pack(fill="x")
        tk.Label(logo, text="⚙", font=("Segoe UI", 22), bg=PAL["sidebar"],
                 fg="#4A9ED4").pack()
        tk.Label(logo, text="Plugin Signer", font=("Segoe UI", 11, "bold"),
                 bg=PAL["sidebar"], fg=PAL["sidebar_sel_txt"]).pack()
        tk.Label(logo, text=f"v{APP_VERSION}", font=FONT_SM,
                 bg=PAL["sidebar"], fg=PAL["sidebar_txt"]).pack()

        sep = tk.Frame(self.sidebar, bg=PAL["sidebar_sel"], height=1)
        sep.pack(fill="x", padx=14, pady=(0, 8))

        nav_items = [
            ("dashboard",    "📊", "Dashboard"),
            ("plugins",      "📦", "Plugins"),
            ("certificates", "🔐", "Certificates"),
            ("sign",         "✍", "Sign"),
            ("package",      "🗜", "Package"),
            ("deploy",       "🚀", "Deploy"),
            ("settings",     "⚙", "Settings"),
            ("logs",         "📋", "Logs"),
        ]
        for key, icon, label in nav_items:
            b = tk.Button(
                self.sidebar, text=f"  {icon}  {label}",
                font=FONT_UI, anchor="w",
                bg=PAL["sidebar"], fg=PAL["sidebar_txt"],
                activebackground=PAL["sidebar_sel"],
                activeforeground=PAL["sidebar_sel_txt"],
                relief="flat", bd=0, cursor="hand2", pady=9,
                command=lambda k=key: self._show_panel(k),
            )
            b.pack(fill="x", padx=6, pady=1)
            self._nav_buttons[key] = b

        # Bottom version label
        tk.Label(self.sidebar, text="Mirth Connect Toolkit",
                 font=("Segoe UI", 8), bg=PAL["sidebar"],
                 fg="#3A4A5A").pack(side="bottom", pady=10)

    def _show_panel(self, key):
        for k, p in self._panels.items():
            p.pack_forget()
        if key in self._panels:
            self._panels[key].pack(fill="both", expand=True)
        # Update sidebar highlight
        for k, b in self._nav_buttons.items():
            if k == key:
                b.config(bg=PAL["sidebar_sel"], fg=PAL["sidebar_sel_txt"])
            else:
                b.config(bg=PAL["sidebar"], fg=PAL["sidebar_txt"])
        self._current_panel = key
        titles = {
            "dashboard":    ("Dashboard", "Overview and quick actions"),
            "plugins":      ("Plugins", "Select which plugin folders to process"),
            "certificates": ("Certificates", "Manage signing certificates"),
            "sign":         ("Sign", "Strip old signatures, sign, verify"),
            "package":      ("Package", "Create deployment ZIP"),
            "deploy":       ("Deploy", "Copy to Mirth, import cert, write policy"),
            "settings":     ("Settings", "Configuration and preferences"),
            "logs":         ("Logs", "Real-time operation output"),
        }
        t, s = titles.get(key, (key.title(), ""))
        self._page_title_var.set(t)
        self._page_sub_var.set(f"  —  {s}")

    # ── panel helpers ─────────────────────────────────────────────────────────

    def _panel(self, key):
        """Create and register a panel frame."""
        f = tk.Frame(self.panel_frame, bg=PAL["bg"])
        self._panels[key] = f
        return f

    def _scrollable(self, parent):
        """Return a frame inside a vertical scrollable canvas."""
        canvas = tk.Canvas(parent, bg=PAL["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=PAL["bg"])
        win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_config(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(win, width=canvas.winfo_width())
        inner.bind("<Configure>", on_config)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        inner.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-int(e.delta/120), "units"))
        return inner

    def _section(self, parent, title):
        """A titled card section."""
        wrap = tk.Frame(parent, bg=PAL["white"],
                        highlightbackground=PAL["border"], highlightthickness=1)
        wrap.pack(fill="x", padx=20, pady=(12, 0))
        hdr = tk.Frame(wrap, bg=PAL["bg2"])
        hdr.pack(fill="x")
        tk.Label(hdr, text=title, font=FONT_BOLD, bg=PAL["bg2"],
                 fg=PAL["text"], padx=14, pady=8, anchor="w").pack(side="left")
        body = tk.Frame(wrap, bg=PAL["white"], padx=14, pady=10)
        body.pack(fill="x")
        return body

    def _field(self, parent, label, var, show="", width=None):
        """Label + Entry pair."""
        row = tk.Frame(parent, bg=PAL["white"])
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, font=FONT_SM, bg=PAL["white"],
                 fg=PAL["text2"], width=24, anchor="w").pack(side="left")
        kw = {"textvariable": var, "font": FONT_UI, "relief": "flat",
              "bg": PAL["bg2"], "fg": PAL["text"],
              "highlightbackground": PAL["border"], "highlightthickness": 1}
        if show:
            kw["show"] = show
        if width:
            kw["width"] = width
        e = tk.Entry(row, **kw)
        e.pack(side="left", fill="x", expand=True, ipady=4)
        return e

    def _combo(self, parent, label, var, values):
        row = tk.Frame(parent, bg=PAL["white"])
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, font=FONT_SM, bg=PAL["white"],
                 fg=PAL["text2"], width=24, anchor="w").pack(side="left")
        cb = ttk.Combobox(row, textvariable=var, values=values,
                          font=FONT_UI, state="readonly")
        cb.pack(side="left", fill="x", expand=True)
        return cb

    def _toggle(self, parent, label, desc, var):
        row = tk.Frame(parent, bg=PAL["bg2"],
                       highlightbackground=PAL["border"], highlightthickness=1)
        row.pack(fill="x", pady=2)
        txt_frame = tk.Frame(row, bg=PAL["bg2"])
        txt_frame.pack(side="left", fill="x", expand=True, padx=10, pady=6)
        tk.Label(txt_frame, text=label, font=FONT_UI, bg=PAL["bg2"],
                 fg=PAL["text"], anchor="w").pack(anchor="w")
        tk.Label(txt_frame, text=desc, font=FONT_SM, bg=PAL["bg2"],
                 fg=PAL["text3"], anchor="w").pack(anchor="w")
        cb = tk.Checkbutton(row, variable=var, bg=PAL["bg2"],
                            activebackground=PAL["bg2"],
                            fg=PAL["accent"], selectcolor=PAL["bg2"],
                            relief="flat", bd=0)
        cb.pack(side="right", padx=10)
        return cb

    def _action_btn(self, parent, text, command, width=None):
        kw = {"text": text, "command": command, "font": FONT_BOLD,
              "bg": PAL["accent"], "fg": PAL["white"],
              "activebackground": PAL["accent_h"], "activeforeground": PAL["white"],
              "relief": "flat", "cursor": "hand2", "padx": 18, "pady": 9, "bd": 0}
        if width:
            kw["width"] = width
        b = tk.Button(parent, **kw)
        b.pack(padx=20, pady=(12, 4), anchor="w")
        return b

    def _secondary_btn(self, parent, text, command):
        b = tk.Button(parent, text=text, command=command, font=FONT_UI,
                      bg=PAL["bg2"], fg=PAL["text"],
                      activebackground=PAL["bg3"], relief="flat",
                      highlightbackground=PAL["border"], highlightthickness=1,
                      cursor="hand2", padx=14, pady=7, bd=0)
        return b

    def _status_bar(self, parent):
        v = tk.StringVar(value="")
        bar = tk.Label(parent, textvariable=v, font=FONT_SM,
                       bg=PAL["bg"], fg=PAL["text2"], anchor="w",
                       padx=20, pady=4)
        bar.pack(fill="x", side="bottom")
        return v

    # ── Dashboard panel ───────────────────────────────────────────────────────

    def _build_panel_dashboard(self):
        p = self._panel("dashboard")
        inner = self._scrollable(p)

        # Quick actions
        qa = self._section(inner, "Quick actions")
        row = tk.Frame(qa, bg=PAL["white"])
        row.pack(fill="x", pady=4)

        quick = [
            ("1. Sign selected plugins",      lambda: self._run_sign()),
            ("2. Create ZIP packages",         lambda: self._run_package()),
            ("3. Deploy to Mirth",             lambda: self._run_deploy()),
            ("Run all three steps",            lambda: self._run_all()),
        ]
        for label, cmd in quick:
            b = tk.Button(row, text=label, command=cmd,
                          font=FONT_UI, bg=PAL["accent"], fg=PAL["white"],
                          activebackground=PAL["accent_h"], relief="flat",
                          cursor="hand2", padx=14, pady=8, bd=0)
            b.pack(side="left", padx=(0, 8), pady=4)

        # Status cards
        cards_frame = self._section(inner, "Status")
        self._dash_plugin_count = tk.StringVar(value="—")
        self._dash_cert_status  = tk.StringVar(value="—")
        self._dash_mirth_path   = tk.StringVar(value=self.cfg.get("mirth_dir"))

        cards = tk.Frame(cards_frame, bg=PAL["white"])
        cards.pack(fill="x")
        self._metric_card(cards, "Plugins found",    self._dash_plugin_count)
        self._metric_card(cards, "Certificate",       self._dash_cert_status)
        self._dash_refresh()

        # Workflow guide
        guide = self._section(inner, "Workflow guide")
        steps = [
            ("1", "Settings",     "Configure Mirth path, certificate details, passwords"),
            ("2", "Plugins",      "Check which plugin folders to sign"),
            ("3", "Certificates", "Generate self-signed cert or verify commercial cert"),
            ("4", "Sign",         "Strip old sigs → copy → sign → verify each JAR/WAR"),
            ("5", "Package",      "Create ZIP with signed JARs + install.bat"),
            ("6", "Deploy",       "Copy to Mirth, import cert, write security policy"),
        ]
        for num, title, desc in steps:
            srow = tk.Frame(guide, bg=PAL["white"])
            srow.pack(fill="x", pady=3)
            badge = tk.Label(srow, text=num, font=("Segoe UI", 10, "bold"),
                             bg=PAL["accent"], fg=PAL["white"],
                             width=2, padx=6, pady=3)
            badge.pack(side="left")
            tk.Label(srow, text=f"  {title}", font=FONT_BOLD, bg=PAL["white"],
                     fg=PAL["text"], width=14, anchor="w").pack(side="left")
            tk.Label(srow, text=desc, font=FONT_SM, bg=PAL["white"],
                     fg=PAL["text2"], anchor="w").pack(side="left")

        inner.update_idletasks()

    def _metric_card(self, parent, label, var):
        c = tk.Frame(parent, bg=PAL["bg2"], padx=16, pady=12)
        c.pack(side="left", padx=(0, 10), pady=4)
        tk.Label(c, textvariable=var, font=("Segoe UI", 20, "bold"),
                 bg=PAL["bg2"], fg=PAL["accent"]).pack()
        tk.Label(c, text=label, font=FONT_SM, bg=PAL["bg2"],
                 fg=PAL["text2"]).pack()

    def _dash_refresh(self):
        plugins = self._get_plugin_folders()
        self._dash_plugin_count.set(str(len(plugins)))
        ks = CERTS_DIR / "self-signed" / f"{self.cfg.get('cert_alias')}.jks"
        comm = self.cfg.get("commercial_path", "")
        if self.cfg.get("cert_type") == "commercial" and comm:
            self._dash_cert_status.set("Commercial")
        elif ks.exists():
            self._dash_cert_status.set("Self-signed ✓")
        else:
            self._dash_cert_status.set("Not generated")

    # ── Plugins panel ─────────────────────────────────────────────────────────

    def _build_panel_plugins(self):
        p = self._panel("plugins")
        inner = self._scrollable(p)

        info = self._section(inner, "Plugin source folder")
        tk.Label(info, text=f"Scanning:  {PLUGINS_DIR}",
                 font=FONT_MONO, bg=PAL["white"], fg=PAL["text2"],
                 anchor="w").pack(fill="x", pady=2)
        tk.Label(info,
                 text="Create one subfolder per plugin. Place all JARs, WARs,\n"
                      "plugin.xml and plugin-extension.xml inside it.",
                 font=FONT_SM, bg=PAL["white"], fg=PAL["text2"],
                 justify="left", anchor="w").pack(anchor="w", pady=(4, 0))

        sel = self._section(inner, "Select plugins to process")
        btn_row = tk.Frame(sel, bg=PAL["white"])
        btn_row.pack(fill="x", pady=(0, 8))
        self._secondary_btn(btn_row, "Select all", self._select_all_plugins).pack(side="left", padx=(0, 6))
        self._secondary_btn(btn_row, "Clear all",  self._clear_all_plugins).pack(side="left", padx=(0, 6))
        self._secondary_btn(btn_row, "↻ Refresh",  self._refresh_plugins).pack(side="left")

        self._plugin_list_frame = tk.Frame(sel, bg=PAL["white"])
        self._plugin_list_frame.pack(fill="x")

        self._no_plugins_label = tk.Label(
            self._plugin_list_frame,
            text=f"No plugin subfolders found in:\n{PLUGINS_DIR}\n\n"
                 "Create a subfolder and place your JARs inside it,\nthen click Refresh.",
            font=FONT_SM, bg=PAL["white"], fg=PAL["text3"],
            justify="center", pady=20)

        inner.update_idletasks()

    def _get_plugin_folders(self):
        if not PLUGINS_DIR.exists():
            return []
        return sorted([d.name for d in PLUGINS_DIR.iterdir() if d.is_dir()])

    def _refresh_plugins(self):
        folders = self._get_plugin_folders()
        for w in self._plugin_list_frame.winfo_children():
            w.destroy()
        self._plugin_vars.clear()

        if not folders:
            PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
            self._no_plugins_label = tk.Label(
                self._plugin_list_frame,
                text=f"No plugin subfolders found in:\n{PLUGINS_DIR}\n\n"
                     "Create a subfolder and place your JARs inside it,\nthen click Refresh.",
                font=FONT_SM, bg=PAL["white"], fg=PAL["text3"],
                justify="center", pady=20)
            self._no_plugins_label.pack()
            return

        for name in folders:
            pdir = PLUGINS_DIR / name
            jars = list(pdir.glob("*.jar")) + list(pdir.glob("*.war"))
            var = tk.BooleanVar(value=True)
            self._plugin_vars[name] = var

            row = tk.Frame(self._plugin_list_frame, bg=PAL["white"],
                           highlightbackground=PAL["border"], highlightthickness=1)
            row.pack(fill="x", pady=2)

            cb = tk.Checkbutton(row, variable=var, bg=PAL["white"],
                                activebackground=PAL["white"],
                                selectcolor=PAL["white"], relief="flat", bd=0)
            cb.pack(side="left", padx=8)

            icon = tk.Label(row, text="📦", font=("Segoe UI", 13),
                            bg=PAL["white"])
            icon.pack(side="left")

            info_f = tk.Frame(row, bg=PAL["white"])
            info_f.pack(side="left", fill="x", expand=True, padx=8, pady=6)
            tk.Label(info_f, text=name, font=FONT_BOLD,
                     bg=PAL["white"], fg=PAL["text"], anchor="w").pack(anchor="w")
            tk.Label(info_f, text=f"{len(jars)} file(s): "
                     + ", ".join(f.name for f in jars[:4])
                     + ("..." if len(jars) > 4 else ""),
                     font=FONT_SM, bg=PAL["white"], fg=PAL["text3"],
                     anchor="w").pack(anchor="w")

            # Show signed output if present
            signed_dir = SIGN_DIR / name
            if signed_dir.exists():
                signed_jars = list(signed_dir.glob("*.jar")) + list(signed_dir.glob("*.war"))
                tk.Label(row, text=f"  ✓ {len(signed_jars)} signed",
                         font=FONT_SM, bg=PAL["white"], fg=PAL["ok"],
                         padx=8).pack(side="right")

        self._dash_refresh()

    def _selected_plugins(self):
        return [n for n, v in self._plugin_vars.items() if v.get()]

    def _select_all_plugins(self):
        for v in self._plugin_vars.values():
            v.set(True)

    def _clear_all_plugins(self):
        for v in self._plugin_vars.values():
            v.set(False)

    # ── Certificates panel ────────────────────────────────────────────────────

    def _build_panel_certificates(self):
        p = self._panel("certificates")
        inner = self._scrollable(p)

        # Type selection
        type_sec = self._section(inner, "Certificate type")
        self._cert_type_var = tk.StringVar(value=self.cfg.get("cert_type"))
        type_row = tk.Frame(type_sec, bg=PAL["white"])
        type_row.pack(fill="x")
        for val, label in [("self-signed", "Self-signed (auto-generated)"),
                            ("commercial",  "Commercial (.jks or .p12)")]:
            rb = tk.Radiobutton(type_row, text=label, variable=self._cert_type_var,
                                value=val, font=FONT_UI, bg=PAL["white"],
                                fg=PAL["text"], activebackground=PAL["white"],
                                selectcolor=PAL["white"], command=self._on_cert_type_change)
            rb.pack(side="left", padx=(0, 20))

        # Self-signed fields
        self._cert_self_frame = self._section(inner, "Self-signed certificate settings")
        self._cv = {k: tk.StringVar(value=self.cfg.get(k)) for k in (
            "cert_alias", "cert_cn", "cert_org", "cert_ou",
            "cert_city", "cert_state", "cert_country", "cert_validity",
            "key_alg", "key_size", "sig_alg", "store_pass", "key_pass")}

        self._field(self._cert_self_frame, "Alias", self._cv["cert_alias"])
        self._field(self._cert_self_frame, "Common name (CN)", self._cv["cert_cn"])

        row2 = tk.Frame(self._cert_self_frame, bg=PAL["white"])
        row2.pack(fill="x", pady=3)
        tk.Label(row2, text="Organisation", font=FONT_SM, bg=PAL["white"],
                 fg=PAL["text2"], width=24, anchor="w").pack(side="left")
        tk.Entry(row2, textvariable=self._cv["cert_org"], font=FONT_UI,
                 relief="flat", bg=PAL["bg2"], fg=PAL["text"],
                 highlightbackground=PAL["border"], highlightthickness=1
                 ).pack(side="left", fill="x", expand=True, ipady=4)

        geo_row = tk.Frame(self._cert_self_frame, bg=PAL["white"])
        geo_row.pack(fill="x", pady=3)
        for label, key, w in [("City", "cert_city", 20), ("State", "cert_state", 20), ("Country", "cert_country", 6)]:
            tk.Label(geo_row, text=label, font=FONT_SM, bg=PAL["white"],
                     fg=PAL["text2"]).pack(side="left", padx=(0, 4))
            tk.Entry(geo_row, textvariable=self._cv[key], font=FONT_UI,
                     relief="flat", bg=PAL["bg2"], fg=PAL["text"],
                     highlightbackground=PAL["border"], highlightthickness=1,
                     width=w).pack(side="left", padx=(0, 14), ipady=4)

        alg_row = tk.Frame(self._cert_self_frame, bg=PAL["white"])
        alg_row.pack(fill="x", pady=3)
        for label, key, opts in [
            ("Algorithm", "key_alg",  ["RSA", "EC"]),
            ("Key size",  "key_size", ["2048", "4096"]),
            ("Signature", "sig_alg",  ["SHA256withRSA", "SHA384withRSA", "SHA512withRSA"]),
        ]:
            tk.Label(alg_row, text=label, font=FONT_SM, bg=PAL["white"],
                     fg=PAL["text2"], padx=(0), pady=0).pack(side="left", padx=(0, 4))
            ttk.Combobox(alg_row, textvariable=self._cv[key], values=opts,
                         font=FONT_UI, state="readonly", width=16
                         ).pack(side="left", padx=(0, 14))

        valid_row = tk.Frame(self._cert_self_frame, bg=PAL["white"])
        valid_row.pack(fill="x", pady=3)
        tk.Label(valid_row, text="Validity (days)", font=FONT_SM,
                 bg=PAL["white"], fg=PAL["text2"], width=24, anchor="w").pack(side="left")
        tk.Entry(valid_row, textvariable=self._cv["cert_validity"], font=FONT_UI,
                 relief="flat", bg=PAL["bg2"], fg=PAL["text"],
                 highlightbackground=PAL["border"], highlightthickness=1, width=10
                 ).pack(side="left", ipady=4)
        tk.Label(valid_row, text="  (3650 = 10 years)", font=FONT_SM,
                 bg=PAL["white"], fg=PAL["text3"]).pack(side="left")

        pwd_row = tk.Frame(self._cert_self_frame, bg=PAL["white"])
        pwd_row.pack(fill="x", pady=3)
        tk.Label(pwd_row, text="Store password", font=FONT_SM,
                 bg=PAL["white"], fg=PAL["text2"], width=24, anchor="w").pack(side="left")
        tk.Entry(pwd_row, textvariable=self._cv["store_pass"], font=FONT_UI,
                 relief="flat", bg=PAL["bg2"], fg=PAL["text"], show="●",
                 highlightbackground=PAL["border"], highlightthickness=1
                 ).pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 8))
        tk.Label(pwd_row, text="Key password", font=FONT_SM,
                 bg=PAL["white"], fg=PAL["text2"]).pack(side="left")
        tk.Entry(pwd_row, textvariable=self._cv["key_pass"], font=FONT_UI,
                 relief="flat", bg=PAL["bg2"], fg=PAL["text"], show="●",
                 highlightbackground=PAL["border"], highlightthickness=1
                 ).pack(side="left", fill="x", expand=True, ipady=4, padx=(8, 0))

        warn = tk.Label(self._cert_self_frame,
                        text="⚠  Use a strong password. Protect config/config.json — "
                             "it stores credentials.",
                        font=FONT_SM, bg=PAL["warn_bg"], fg=PAL["warn"],
                        anchor="w", padx=10, pady=6)
        warn.pack(fill="x", pady=(6, 0))

        # Commercial certificate fields
        self._cert_comm_frame = self._section(inner, "Commercial certificate")
        self._comm_path_var   = tk.StringVar(value=self.cfg.get("commercial_path"))
        self._comm_alias_var  = tk.StringVar(value=self.cfg.get("commercial_alias"))

        comm_row = tk.Frame(self._cert_comm_frame, bg=PAL["white"])
        comm_row.pack(fill="x", pady=3)
        tk.Label(comm_row, text="Path to .jks / .p12",
                 font=FONT_SM, bg=PAL["white"], fg=PAL["text2"],
                 width=24, anchor="w").pack(side="left")
        tk.Entry(comm_row, textvariable=self._comm_path_var,
                 font=FONT_UI, relief="flat", bg=PAL["bg2"], fg=PAL["text"],
                 highlightbackground=PAL["border"], highlightthickness=1
                 ).pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 6))
        tk.Button(comm_row, text="Browse…",
                  command=lambda: self._browse_cert(),
                  font=FONT_SM, bg=PAL["bg3"], fg=PAL["text"],
                  relief="flat", cursor="hand2", padx=8, pady=5
                  ).pack(side="left")
        self._field(self._cert_comm_frame, "Certificate alias", self._comm_alias_var)

        # Actions
        act = self._section(inner, "Actions")
        btn_row = tk.Frame(act, bg=PAL["white"])
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="Generate self-signed certificate",
                  command=self._run_generate_cert,
                  font=FONT_BOLD, bg=PAL["accent"], fg=PAL["white"],
                  activebackground=PAL["accent_h"], relief="flat",
                  cursor="hand2", padx=18, pady=9, bd=0
                  ).pack(side="left", padx=(0, 10), pady=4)
        tk.Button(btn_row, text="Verify certificate",
                  command=self._run_verify_cert,
                  font=FONT_UI, bg=PAL["bg2"], fg=PAL["text"],
                  activebackground=PAL["bg3"], relief="flat",
                  highlightbackground=PAL["border"], highlightthickness=1,
                  cursor="hand2", padx=14, pady=8
                  ).pack(side="left", pady=4)

        self._on_cert_type_change()
        inner.update_idletasks()

    def _on_cert_type_change(self):
        t = self._cert_type_var.get()
        if t == "self-signed":
            self._cert_self_frame.pack(fill="x", padx=20, pady=(12, 0))
            self._cert_comm_frame.pack_forget()
        else:
            self._cert_comm_frame.pack(fill="x", padx=20, pady=(12, 0))

    def _browse_cert(self):
        f = filedialog.askopenfilename(
            title="Select certificate",
            filetypes=[("Keystores", "*.jks *.p12"), ("All files", "*.*")])
        if f:
            self._comm_path_var.set(f)

    # ── Sign panel ────────────────────────────────────────────────────────────

    def _build_panel_sign(self):
        p = self._panel("sign")
        inner = self._scrollable(p)

        # Options
        opts = self._section(inner, "Signing options")
        self._sign_opts = {
            "opt_strip_sigs": tk.BooleanVar(value=self.cfg.get("opt_strip_sigs")),
            "opt_verify":     tk.BooleanVar(value=self.cfg.get("opt_verify")),
            "opt_sign_war":   tk.BooleanVar(value=self.cfg.get("opt_sign_war")),
        }
        self._toggle(opts, "Strip existing signatures before re-signing",
                     "Removes .SF / .RSA / .DSA / .EC from META-INF to avoid 'multiple signers' errors",
                     self._sign_opts["opt_strip_sigs"])
        self._toggle(opts, "Verify every file after signing",
                     "Runs jarsigner -verify on each output file and fails if not valid",
                     self._sign_opts["opt_verify"])
        self._toggle(opts, "Sign .war files too",
                     "WAR archives are ZIP-based and can be signed with jarsigner",
                     self._sign_opts["opt_sign_war"])

        # TSA
        tsa_sec = self._section(inner, "Timestamp server (TSA)")
        self._tsa_var = tk.StringVar(value=self.cfg.get("tsa_server"))
        tsa_row = tk.Frame(tsa_sec, bg=PAL["white"])
        tsa_row.pack(fill="x", pady=4)
        for name, url in TSA_SERVERS.items():
            tk.Button(tsa_row, text=name,
                      command=lambda u=url: self._tsa_var.set(u),
                      font=FONT_SM, bg=PAL["bg2"], fg=PAL["text"],
                      relief="flat", cursor="hand2", padx=10, pady=5,
                      highlightbackground=PAL["border"], highlightthickness=1
                      ).pack(side="left", padx=(0, 6))
        self._field(tsa_sec, "TSA URL (blank = no timestamp)", self._tsa_var)

        # Output path info
        out_info = self._section(inner, "Output location")
        tk.Label(out_info,
                 text=f"Signed files are written to:\n{SIGN_DIR}\\<plugin-name>\\",
                 font=FONT_MONO, bg=PAL["white"], fg=PAL["text2"],
                 anchor="w", justify="left").pack(anchor="w")
        tk.Label(out_info,
                 text="Source files in plugins\\ are never modified.",
                 font=FONT_SM, bg=PAL["white"], fg=PAL["ok"],
                 anchor="w").pack(anchor="w", pady=(4, 0))

        # Action
        act = self._section(inner, "Run")
        tk.Button(act, text="Sign selected plugins",
                  command=self._run_sign,
                  font=FONT_BOLD, bg=PAL["accent"], fg=PAL["white"],
                  activebackground=PAL["accent_h"], relief="flat",
                  cursor="hand2", padx=20, pady=10, bd=0
                  ).pack(side="left", pady=4, padx=(0, 10))
        tk.Button(act, text="Verify signed files",
                  command=lambda: self._run_in_thread(
                      lambda: self.engine.verify_signed(self._selected_plugins()),
                      "Verifying..."),
                  font=FONT_UI, bg=PAL["bg2"], fg=PAL["text"],
                  activebackground=PAL["bg3"], relief="flat",
                  highlightbackground=PAL["border"], highlightthickness=1,
                  cursor="hand2", padx=14, pady=9
                  ).pack(side="left", pady=4)

        inner.update_idletasks()

    # ── Package panel ─────────────────────────────────────────────────────────

    def _build_panel_package(self):
        p = self._panel("package")
        inner = self._scrollable(p)

        opts = self._section(inner, "Package options")
        self._pkg_opts = {
            "opt_create_zip":      tk.BooleanVar(value=self.cfg.get("opt_create_zip")),
            "opt_include_install": tk.BooleanVar(value=self.cfg.get("opt_include_install")),
        }
        self._toggle(opts, "Create ZIP package",
                     "Packages signed JARs + descriptors + certificate into a distributable ZIP",
                     self._pkg_opts["opt_create_zip"])
        self._toggle(opts, "Include install.bat inside ZIP",
                     "Adds a one-click installer for end users (copies JARs + imports cert)",
                     self._pkg_opts["opt_include_install"])

        ver_sec = self._section(inner, "Version")
        self._version_var = tk.StringVar(value=self.cfg.get("plugin_version"))
        self._field(ver_sec, "Plugin version", self._version_var)

        out_info = self._section(inner, "Output")
        tk.Label(out_info,
                 text=f"ZIP saved to:\n{SIGN_DIR}\\<plugin-name>\\<plugin-name>-v<version>.zip",
                 font=FONT_MONO, bg=PAL["white"], fg=PAL["text2"],
                 anchor="w", justify="left").pack(anchor="w")

        act = self._section(inner, "Run")
        tk.Button(act, text="Create ZIP packages",
                  command=self._run_package,
                  font=FONT_BOLD, bg=PAL["accent"], fg=PAL["white"],
                  activebackground=PAL["accent_h"], relief="flat",
                  cursor="hand2", padx=20, pady=10, bd=0
                  ).pack(side="left", pady=4)

        inner.update_idletasks()

    # ── Deploy panel ──────────────────────────────────────────────────────────

    def _build_panel_deploy(self):
        p = self._panel("deploy")
        inner = self._scrollable(p)

        mirth = self._section(inner, "Target")
        self._mirth_dir_var2 = tk.StringVar(value=self.cfg.get("mirth_dir"))
        mirth_row = tk.Frame(mirth, bg=PAL["white"])
        mirth_row.pack(fill="x", pady=3)
        tk.Label(mirth_row, text="Mirth / BridgeLink path",
                 font=FONT_SM, bg=PAL["white"], fg=PAL["text2"],
                 width=24, anchor="w").pack(side="left")
        tk.Entry(mirth_row, textvariable=self._mirth_dir_var2,
                 font=FONT_UI, relief="flat", bg=PAL["bg2"], fg=PAL["text"],
                 highlightbackground=PAL["border"], highlightthickness=1
                 ).pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 6))
        tk.Button(mirth_row, text="Browse…",
                  command=lambda: self._browse_mirth_dir(self._mirth_dir_var2),
                  font=FONT_SM, bg=PAL["bg3"], fg=PAL["text"],
                  relief="flat", cursor="hand2", padx=8, pady=5
                  ).pack(side="left")

        opts = self._section(inner, "Deployment options")
        self._dep_opts = {
            "opt_import_cert":  tk.BooleanVar(value=self.cfg.get("opt_import_cert")),
            "opt_write_policy": tk.BooleanVar(value=self.cfg.get("opt_write_policy")),
            "opt_dedup_props":  tk.BooleanVar(value=self.cfg.get("opt_dedup_props")),
            "opt_backup_props": tk.BooleanVar(value=self.cfg.get("opt_backup_props")),
            "opt_restart_mirth":tk.BooleanVar(value=self.cfg.get("opt_restart_mirth")),
        }
        self._toggle(opts, "Import certificate to Mirth JRE truststore",
                     "Imports .cer to cacerts; auto-detects jre, jre17, jre21, jre11",
                     self._dep_opts["opt_import_cert"])
        self._toggle(opts, "Write security policy (custom.policy)",
                     "Creates a scoped policy — AllPermission only for your plugin's codeBase",
                     self._dep_opts["opt_write_policy"])
        self._toggle(opts, "Prevent duplicate mirth.properties entries",
                     "Only adds java.security.policy if it is not already present",
                     self._dep_opts["opt_dedup_props"])
        self._toggle(opts, "Backup mirth.properties before changes",
                     "Saves .backup copy once — does not overwrite an existing backup",
                     self._dep_opts["opt_backup_props"])
        self._toggle(opts, "Restart Mirth Connect service after deploy",
                     "Runs: net stop 'Mirth Connect Service'  /  net start ... (Windows only)",
                     self._dep_opts["opt_restart_mirth"])

        note = self._section(inner, "Note")
        tk.Label(note,
                 text="Run this tool as Administrator when deploying — writing to\n"
                      "Program Files and editing mirth.properties requires elevated access.",
                 font=FONT_SM, bg=PAL["warn_bg"], fg=PAL["warn"],
                 anchor="w", justify="left", padx=10, pady=8
                 ).pack(fill="x")

        act = self._section(inner, "Run")
        tk.Button(act, text="Deploy to Mirth",
                  command=self._run_deploy,
                  font=FONT_BOLD, bg=PAL["accent"], fg=PAL["white"],
                  activebackground=PAL["accent_h"], relief="flat",
                  cursor="hand2", padx=20, pady=10, bd=0
                  ).pack(side="left", pady=4)

        inner.update_idletasks()

    def _browse_mirth_dir(self, var):
        d = filedialog.askdirectory(title="Select Mirth Connect directory")
        if d:
            var.set(d)

    # ── Settings panel ────────────────────────────────────────────────────────

    def _build_panel_settings(self):
        p = self._panel("settings")
        inner = self._scrollable(p)

        paths = self._section(inner, "Paths")
        self._set_mirth_var = tk.StringVar(value=self.cfg.get("mirth_dir"))
        mrow = tk.Frame(paths, bg=PAL["white"])
        mrow.pack(fill="x", pady=3)
        tk.Label(mrow, text="Mirth / BridgeLink directory",
                 font=FONT_SM, bg=PAL["white"], fg=PAL["text2"],
                 width=28, anchor="w").pack(side="left")
        tk.Entry(mrow, textvariable=self._set_mirth_var,
                 font=FONT_UI, relief="flat", bg=PAL["bg2"], fg=PAL["text"],
                 highlightbackground=PAL["border"], highlightthickness=1
                 ).pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 6))
        tk.Button(mrow, text="Browse…",
                  command=lambda: self._browse_mirth_dir(self._set_mirth_var),
                  font=FONT_SM, bg=PAL["bg3"], fg=PAL["text"],
                  relief="flat", cursor="hand2", padx=8, pady=5
                  ).pack(side="left")

        # Read-only path info
        for label, path in [
            ("Plugins folder",      PLUGINS_DIR),
            ("Signed output folder",SIGN_DIR),
            ("Certificates folder", CERTS_DIR),
            ("Config file",         CONFIG_FILE),
        ]:
            r = tk.Frame(paths, bg=PAL["white"])
            r.pack(fill="x", pady=2)
            tk.Label(r, text=label, font=FONT_SM, bg=PAL["white"],
                     fg=PAL["text2"], width=28, anchor="w").pack(side="left")
            tk.Label(r, text=str(path), font=FONT_MONO, bg=PAL["white"],
                     fg=PAL["text3"], anchor="w").pack(side="left")

        java = self._section(inner, "Java / JDK")
        tk.Label(java,
                 text="keytool and jarsigner must be on your PATH (or JAVA_HOME must be set).",
                 font=FONT_SM, bg=PAL["white"], fg=PAL["text2"],
                 anchor="w").pack(anchor="w")
        tk.Button(java, text="Check Java tools",
                  command=lambda: self._run_in_thread(self.engine.check_java, "Checking Java..."),
                  font=FONT_UI, bg=PAL["bg2"], fg=PAL["text"],
                  activebackground=PAL["bg3"], relief="flat",
                  highlightbackground=PAL["border"], highlightthickness=1,
                  cursor="hand2", padx=14, pady=7
                  ).pack(anchor="w", pady=(8, 0))

        about = self._section(inner, "About")
        about_lines = [
            f"Mirth Connect Plugin Signer  v{APP_VERSION}",
            "",
            "Signs, packages and deploys Mirth Connect / BridgeLink plugin JARs.",
            "No external .bat files required — this Python script is the complete tool.",
            "",
            "Requirements: Python 3.8+ · JDK (keytool, jarsigner) · tkinter",
            "",
            "Config stored in:  config/config.json",
            "Source plugins in: plugins/<name>/",
            "Signed output in:  sign/<name>/",
        ]
        for line in about_lines:
            tk.Label(about, text=line, font=FONT_SM, bg=PAL["white"],
                     fg=PAL["text2" if line else "text3"], anchor="w"
                     ).pack(anchor="w", pady=1)

        act = self._section(inner, "Save / Reset")
        btn_row = tk.Frame(act, bg=PAL["white"])
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="Save settings",
                  command=self._save_all_settings,
                  font=FONT_BOLD, bg=PAL["accent"], fg=PAL["white"],
                  activebackground=PAL["accent_h"], relief="flat",
                  cursor="hand2", padx=18, pady=9, bd=0
                  ).pack(side="left", padx=(0, 10), pady=4)
        tk.Button(btn_row, text="Reset to defaults",
                  command=self._reset_settings,
                  font=FONT_UI, bg=PAL["bg2"], fg=PAL["warn"],
                  activebackground=PAL["bg3"], relief="flat",
                  highlightbackground=PAL["border"], highlightthickness=1,
                  cursor="hand2", padx=14, pady=8
                  ).pack(side="left", pady=4)

        inner.update_idletasks()

    # ── Logs panel ────────────────────────────────────────────────────────────

    def _build_panel_logs(self):
        p = self._panel("logs")

        toolbar = tk.Frame(p, bg=PAL["bg"], pady=6)
        toolbar.pack(fill="x", padx=20)
        tk.Label(toolbar, text="Operation log", font=FONT_BOLD,
                 bg=PAL["bg"], fg=PAL["text"]).pack(side="left")
        tk.Button(toolbar, text="Clear", font=FONT_SM,
                  command=self._clear_logs,
                  bg=PAL["bg2"], fg=PAL["text"], relief="flat",
                  highlightbackground=PAL["border"], highlightthickness=1,
                  cursor="hand2", padx=10, pady=4
                  ).pack(side="right")
        tk.Button(toolbar, text="Save log…", font=FONT_SM,
                  command=self._save_log,
                  bg=PAL["bg2"], fg=PAL["text"], relief="flat",
                  highlightbackground=PAL["border"], highlightthickness=1,
                  cursor="hand2", padx=10, pady=4
                  ).pack(side="right", padx=(0, 8))

        self.log_text = scrolledtext.ScrolledText(
            p,
            bg=PAL["log_bg"], fg=PAL["log_fg"],
            font=FONT_MONO,
            wrap="word",
            state="disabled",
            relief="flat",
            padx=12, pady=10,
        )
        self.log_text.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        # Configure colour tags
        for tag, color in [
            ("ok",   PAL["log_ok"]),
            ("warn", PAL["log_warn"]),
            ("err",  PAL["log_err"]),
            ("info", PAL["log_fg"]),
            ("step", PAL["log_step"]),
        ]:
            self.log_text.tag_config(tag, foreground=color)

    def _enqueue_log(self, level, message):
        """Thread-safe: put a log message on the queue."""
        self.log_queue.put((level, message))

    def _poll_log_queue(self):
        """Drain the log queue every 50ms and write to the log widget."""
        while not self.log_queue.empty():
            level, msg = self.log_queue.get_nowait()
            self._append_log(level, msg)
        self.after(50, self._poll_log_queue)

    def _append_log(self, level, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        prefix = {"step": "►", "ok": "✓", "warn": "⚠", "err": "✗", "info": " "}.get(level, " ")
        line = f"[{ts}] {prefix} {msg}\n"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line, level)
        self.log_text.configure(state="disabled")
        self.log_text.see("end")

    def _clear_logs(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _save_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All", "*.*")],
            initialfile=f"signer-log-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.txt",
        )
        if path:
            content = self.log_text.get("1.0", "end")
            pathlib.Path(path).write_text(content, encoding="utf-8")

    # ── Operations ────────────────────────────────────────────────────────────

    def _sync_config_from_ui(self):
        """Write all UI values back into ConfigManager before any operation."""
        # Certificate tab
        if hasattr(self, "_cert_type_var"):
            self.cfg.set("cert_type", self._cert_type_var.get())
        for key, var in getattr(self, "_cv", {}).items():
            self.cfg.set(key, var.get())
        for attr, key in [("_comm_path_var", "commercial_path"),
                          ("_comm_alias_var", "commercial_alias"),
                          ("_tsa_var", "tsa_server"),
                          ("_version_var", "plugin_version")]:
            if hasattr(self, attr):
                self.cfg.set(key, getattr(self, attr).get())
        # Sign opts
        for key, var in getattr(self, "_sign_opts", {}).items():
            self.cfg.set(key, var.get())
        # Package opts
        for key, var in getattr(self, "_pkg_opts", {}).items():
            self.cfg.set(key, var.get())
        # Deploy opts
        for key, var in getattr(self, "_dep_opts", {}).items():
            self.cfg.set(key, var.get())
        # Mirth dirs
        for attr, key in [("_mirth_dir_var2", "mirth_dir"),
                          ("_set_mirth_var",  "mirth_dir")]:
            if hasattr(self, attr):
                v = getattr(self, attr).get()
                if v:
                    self.cfg.set(key, v)

    def _save_all_settings(self):
        self._sync_config_from_ui()
        self.cfg.save()
        self._append_log("ok", "Settings saved to config/config.json")
        messagebox.showinfo("Saved", "Settings saved to config/config.json")

    def _reset_settings(self):
        if messagebox.askyesno("Reset", "Reset all settings to defaults?"):
            if CONFIG_FILE.exists():
                CONFIG_FILE.unlink()
            self.cfg = ConfigManager()
            messagebox.showinfo("Reset", "Settings reset. Restart to apply.")

    def _get_selected_or_warn(self):
        sel = self._selected_plugins()
        if not sel:
            messagebox.showwarning("No plugins selected",
                                   "Go to the Plugins tab and select at least one plugin.")
        return sel

    def _run_in_thread(self, fn, status_msg="Working…"):
        self._show_panel("logs")
        self._enqueue_log("step", status_msg)
        self._sync_config_from_ui()

        def worker():
            try:
                fn()
            except Exception as e:
                self._enqueue_log("err", f"Unexpected error: {e}")
            finally:
                self._enqueue_log("info", "─" * 52)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _run_generate_cert(self):
        self._run_in_thread(self.engine.generate_certificate, "Generating certificate...")

    def _run_verify_cert(self):
        def do():
            self.engine.check_java()
            ks = self.engine._keystore_path()
            if ks.exists():
                self._enqueue_log("ok", f"Keystore found: {ks}")
            else:
                self._enqueue_log("err", f"Keystore NOT found: {ks}")
            cer = self.engine._cer_path()
            if cer.exists():
                self._enqueue_log("ok", f"Certificate (.cer) found: {cer}")
            else:
                self._enqueue_log("warn", "Certificate (.cer) not exported yet.")
        self._run_in_thread(do, "Verifying certificate...")

    def _run_sign(self):
        sel = self._get_selected_or_warn()
        if not sel:
            return
        self._run_in_thread(
            lambda: self.engine.sign_plugins(sel),
            f"Signing {len(sel)} plugin(s)...")

    def _run_package(self):
        sel = self._get_selected_or_warn()
        if not sel:
            return
        self._run_in_thread(
            lambda: self.engine.create_packages(sel),
            f"Packaging {len(sel)} plugin(s)...")

    def _run_deploy(self):
        sel = self._get_selected_or_warn()
        if not sel:
            return
        self._run_in_thread(
            lambda: self.engine.deploy_plugins(sel),
            f"Deploying {len(sel)} plugin(s)...")

    def _run_all(self):
        sel = self._get_selected_or_warn()
        if not sel:
            return
        def all_steps():
            self.engine.sign_plugins(sel)
            self.engine.create_packages(sel)
            if self.cfg.get("opt_auto_deploy"):
                self.engine.deploy_plugins(sel)
            else:
                self._enqueue_log("info",
                    "Auto-deploy is OFF. Enable it in Deploy tab to also deploy.")
        self._run_in_thread(all_steps, f"Running all steps for {len(sel)} plugin(s)...")

    def _run_verify_cert(self):
        def do():
            ok = self.engine.check_java()
            if not ok:
                return
            ks = self.engine._keystore_path()
            self._enqueue_log("ok" if ks.exists() else "err",
                              f"Keystore: {ks}  ({'found' if ks.exists() else 'NOT found'})")
            cer = self.engine._cer_path()
            self._enqueue_log("ok" if cer.exists() else "warn",
                              f"Certificate: {cer}  ({'found' if cer.exists() else 'not exported'})")
        self._run_in_thread(do, "Checking certificate...")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    """
    Entry point.
    On Windows, tkinter is bundled with the standard Python installer.
    On Linux, install with:  sudo apt install python3-tk
    On macOS, install Python from python.org (includes tkinter).
    """
    try:
        import tkinter  # noqa
    except ImportError:
        print("ERROR: tkinter not found.")
        print("  Windows:  reinstall Python from python.org (check 'tcl/tk' option)")
        print("  Linux:    sudo apt install python3-tk")
        print("  macOS:    install Python from python.org")
        sys.exit(1)

    app = MirthSignerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
