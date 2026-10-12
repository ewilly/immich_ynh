#!/usr/bin/env python3
"""Met à jour manifest.toml depuis le manifest.json d'une release immich-build.

À placer dans .github/workflows/autoupdate_from_build.py

Usage:
    autoupdate_from_build.py --upstream-manifest upstream-manifest.json \
                             --manifest manifest.toml \
                             [--force]

Sortie (GITHUB_OUTPUT si défini, sinon stdout):
    updated=true|false
    old_version=X.Y.Z
    new_version=X.Y.Z

Le remplacement se fait par substitution de chaînes (et non par réécriture
TOML) afin de préserver tabulations, commentaires et ordre des clés.
"""

import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path

# (clé dans le manifest.json, nom de la source dans manifest.toml)
SUITES = [
    ("bookworm", "immich_prebuilt_bookworm"),
    ("trixie", "immich_prebuilt_trixie"),
]
ARCHES = ["amd64", "arm64"]


def version_tuple(version: str) -> tuple[int, ...]:
    """'3.3.10' -> (3, 3, 10). Comparaison numérique, pas lexicographique."""
    parts = [p for p in re.split(r"[.\-]", version) if p.isdigit()]
    if not parts:
        sys.exit(f"Version non comparable : '{version}'")
    return tuple(int(p) for p in parts)


def set_output(**values: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{key}={value}\n" for key, value in values.items()]
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.writelines(lines)
    else:
        sys.stdout.writelines(lines)


def build_replacements(manifest: dict, upstream: dict) -> list[tuple[str, str]]:
    """Liste des (ancienne valeur, nouvelle valeur) à substituer."""
    resources = manifest["resources"]
    sources = resources["sources"]

    replacements = [(resources["nodejs"]["version"], upstream["node_version"])]

    for suite, source_name in SUITES:
        for arch in ARCHES:
            current = sources[source_name][arch]
            replacements.append((current["url"], upstream[suite][f"{arch}_url"]))
            replacements.append(
                (current["sha256"], upstream[suite][f"{arch}_sha256"])
            )

    return replacements


def bump_version(content: str, new_version: str) -> str:
    """version = "3.3.0~ynh2"  ->  version = "3.3.1~ynh1" """
    content, count = re.subn(
        r'(version\s*=\s*")[^"~]+(?:~ynh\d+)?(")',
        rf"\g<1>{new_version}~ynh1\g<2>",
        content,
        count=1,
    )
    if count != 1:
        sys.exit("Impossible de localiser la clé 'version' dans manifest.toml")
    return content


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--upstream-manifest",
        type=Path,
        default=Path("upstream-manifest.json"),
        help="manifest.json téléchargé depuis la release immich-build",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("manifest.toml"),
        help="manifest.toml du paquet à mettre à jour",
    )
    parser.add_argument(
        "--new-version",
        help="Version amont. Par défaut, lue dans la clé 'immich_version'.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Mettre à jour même si la version locale est >= à la version amont",
    )
    args = parser.parse_args()

    upstream = json.loads(args.upstream_manifest.read_text(encoding="utf-8"))
    raw = args.manifest.read_text(encoding="utf-8")
    manifest = tomllib.loads(raw)

    new_version = args.new_version or upstream["immich_version"]
    old_version = manifest["version"].split("~")[0]

    print(f"manifest.toml : {old_version}")
    print(f"immich-build  : {new_version}")

    if not args.force and version_tuple(old_version) >= version_tuple(new_version):
        print("Déjà à jour, rien à faire.")
        set_output(updated="false", old_version=old_version, new_version=new_version)
        return

    for old, new in build_replacements(manifest, upstream):
        if old == new:
            continue
        if old not in raw:
            sys.exit(f"Valeur introuvable dans manifest.toml : {old}")
        raw = raw.replace(old, new)

    raw = bump_version(raw, new_version)
    args.manifest.write_text(raw, encoding="utf-8")

    print(f"manifest.toml mis à jour : {old_version} -> {new_version}~ynh1")
    set_output(updated="true", old_version=old_version, new_version=new_version)


if __name__ == "__main__":
    main()
