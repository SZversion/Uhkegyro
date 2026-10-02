import json
import sys


def main():
    if len(sys.argv) == 1 or not sys.argv[1]:
        print("mcp")
        return
    with open(sys.argv[1], encoding="utf-8") as service_file:
        service = json.load(service_file)
    containers = service.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    ingress = [container for container in containers if container.get("ports")]
    if len(ingress) != 1:
        sys.exit("Cloud Run service must have exactly one ingress container")
    print(ingress[0].get("name") or "__default__")


if __name__ == "__main__":
    main()
