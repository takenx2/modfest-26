#!/usr/bin/env python3
import json
import os
import zipfile
from typing import Any
from zipfile import ZipFile

import requests

import common


def main():
	repo_root = common.get_repo_root()
	constants_file = repo_root / "constants.jsonc"
	pack_toml_file = repo_root / "pack" / "pack.toml"
	generated_dir = common.get_generated_dir()
	repo_name = os.path.basename(repo_root.resolve())

	branch_name = common.get_current_git_branch()
	test_mode = "test" in branch_name

	for (url, ext) in [
		[f"https://modfest.github.io/{repo_name}/pack.toml", "Test" if test_mode else ""],
		[f"http://localhost:8080/pack.toml", "Debug"]
	]:
		print(f"Generating packs for {url}")

		packwiz_info = common.parse_packwiz(pack_toml_file)
		constants = common.jsonc_at_home(common.read_file(constants_file))

		# Create prism zip
		prism = generated_dir / f"{packwiz_info.safe_name()}{(('-' + ext) if ext else '')}.zip"
		with ZipFile(prism, "w", compression=zipfile.ZIP_DEFLATED) as output_zip:
			icon_key = packwiz_info.safe_name()

			with output_zip.open("instance.cfg", mode="w") as cfg:
				cfg.write(create_instance_config(packwiz_info, icon_key).encode("utf-8"))

			with output_zip.open("mmc-pack.json", mode="w") as packjson:
				packjson.write(create_mmc_meta(packwiz_info, packwiz_info.unsup).encode("utf-8"))

			art_id = constants["art_id"]
			with output_zip.open(f"{icon_key}.png", mode="w") as f:
				f.write(requests.get(f'https://github.com/ModFest/art/blob/v2/icon/64w/{art_id}/transparent.png?raw=true').content)

			if packwiz_info.unsup:
				with output_zip.open("patches/com.unascribed.unsup.json", mode="w") as patch:
					patch.write(create_unsup_patch(packwiz_info.unsup).encode("utf-8"))

			with output_zip.open(".minecraft/unsup.ini", mode="w") as unsupini:
				unsupini.write(create_unsup_ini(url, constants, packwiz_info).encode("utf-8"))
		print(f"Wrote to \"{prism.relative_to(generated_dir)}\"")

		# Download unsup jar for server
		unsup_jar_file = generated_dir / "cache" / f"unsup-{packwiz_info.unsup}.jar"
		if not unsup_jar_file.exists():
			unsup_jar_file.parent.mkdir(exist_ok=True, parents=True)
			print(f"Downloading unsup to {unsup_jar_file.relative_to(repo_root)}")
			with open(unsup_jar_file, "wb") as f:
				f.write(requests.get(f"https://repo.sleeping.town/com/unascribed/unsup/{packwiz_info.unsup}/unsup-{packwiz_info.unsup}.jar").content)

		server_zip = generated_dir / f"{packwiz_info.safe_name()}{('-' + ext) if ext else ''}-Server.zip"
		with ZipFile(server_zip, "w", compression=zipfile.ZIP_DEFLATED) as output_zip:
			if packwiz_info.loader == "fabric":
				with output_zip.open("fabric-server-launcher.jar", mode="w") as f:
					f.write(requests.get(f"https://meta.fabricmc.net/v2/versions/loader/{packwiz_info.minecraft_version}/{packwiz_info.loader_version}/1.0.1/server/jar").content)
				with output_zip.open("start.bat", mode="w") as start_out:
					start_out.write(f"@echo off\njava -Xmx4096M -Xms4096M -javaagent:unsup.jar -jar fabric-server-launcher.jar nogui\npause".encode("utf-8"))
				with output_zip.open("start.sh", mode="w") as start_out:
					start_out.write(f"#!/usr/bin/env\njava -Xmx4096M -Xms4096M -javaagent:unsup.jar -jar fabric-server-launcher.jar nogui".encode("utf-8"))
			elif packwiz_info.loader == "neoforge":
				with output_zip.open("neoforge-installer.jar", mode="w") as f:
					f.write(requests.get(f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{packwiz_info.loader_version}/neoforge-{packwiz_info.loader_version}-installer.jar").content)
				with output_zip.open("user_jvm_args.txt", mode="w") as jvm_args:
					jvm_args.write("-javaagent:unsup.jar".encode("utf-8"))
				with output_zip.open("install.bat", mode="w") as start_out:
					start_out.write("java -jar neoforge-installer.jar --install-server".encode("utf-8"))
				with output_zip.open("install.sh", mode="w") as start_out:
					start_out.write("#!/usr/bin/env\njava -jar neoforge-installer.jar --install-server".encode("utf-8"))
				with output_zip.open("start.bat", mode="w") as start_out:
					start_out.write(f"CALL run.bat nogui".encode("utf-8"))
				with output_zip.open("start.sh", mode="w") as start_out:
					start_out.write(f"#!/usr/bin/env\n./run.sh nogui".encode("utf-8"))

			with output_zip.open("unsup.jar", mode="w") as unsup_out:
				with open(unsup_jar_file, "rb") as unsup_src:
					unsup_out.write(unsup_src.read())

			with output_zip.open("unsup.ini", mode="w") as unsupini:
				unsupini.write(create_unsup_ini(url, constants, packwiz_info).encode("utf-8"))
		print(f"Wrote to \"{server_zip.relative_to(generated_dir)}\"")


# Creates a patch file which tells prism to
# load unsup as an agent
def create_unsup_patch(unsup_version):
	patch = {
		"formatVersion": 1,
		"name": "unsup",
		"uid": "com.unascribed.unsup",
		"version": unsup_version,
		"+agents": [
			{
				"name": f"com.unascribed:unsup:{unsup_version}",
				"url": "https://repo.sleeping.town"
			}
		]
	}
	return json.dumps(patch)


# Creates the mmc-pack.json file, which stores "dependency" information for prism/multimc
# The most important thing is that it defines the minecraft version and launcher used
def create_mmc_meta(packwiz_info, unsup):
	meta: Any = {"formatVersion": 1}

	components = [{
		"important": True,
		"uid": "net.minecraft",
		"version": packwiz_info.minecraft_version
	}, {
		"cachedName": "unsup",
		"cachedVersion": unsup,
		"uid": "com.unascribed.unsup"
	}]

	# Add loader component
	if packwiz_info.loader == "neoforge":
		components.append({
			"uid": "net.neoforged",
			"version": packwiz_info.loader_version
		})
	elif packwiz_info.loader == "fabric":
		components.append({
			"uid": "net.fabricmc.fabric-loader",
			"version": packwiz_info.loader_version
		})
	else:
		raise RuntimeError(f"Unknown loader {packwiz_info.loader}")

	meta["components"] = components
	return json.dumps(meta)


# Creates the instance.cfg, which defines basic information about the pack
# to prism/multimc
def create_instance_config(packwiz_info, icon_name):
	return instance_cfg_template.replace("{iconKey}", icon_name).replace("{name}", packwiz_info.name)


# Creates the unsup config file, which tells unsup where
# to download mods from
def create_unsup_ini(url: str, constants, info):
	colour_entries = []
	for color_key in unsup_colors:
		color_value = common.get_colour(constants, "_unsup_" + color_key)
		if color_value:
			color_value = color_value.replace("#", "")
			colour_entries.append(f"{color_key}={color_value}")
	return unsup_ini_template.replace("{name}", info.name).replace("{icon}", constants["icon"]).replace("{url}", url).replace("{colors}", "\n".join(colour_entries))


instance_cfg_template = """
[General]
ConfigVersion=1.2
iconKey={iconKey}
name={name}
InstanceType=OneSix
""".strip()

unsup_colors = [
	"background",
	"title",
	"subtitle",
	"progress",
	"progress_track",
	"dialog",
	"button",
	"button_text",
]

unsup_ini_template = """
version=1
source_format=packwiz
source={url}
preset=minecraft
[branding]
modpack_name={name}
icon={icon}
[colors]
{colors}
""".strip()

if __name__ == "__main__":
	main()
