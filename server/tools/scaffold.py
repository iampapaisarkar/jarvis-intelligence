"""Write starter files for common project kinds. No package installs."""

from __future__ import annotations

import json
from pathlib import Path

from server.tools.catalog import normalize_project_kind


def write_project(root: Path, name: str, kind: str) -> list[str]:
    resolved = normalize_project_kind(kind)
    writers = {
        "node": write_node_project,
        "python": write_python_project,
        "react": write_react_project,
        "next": write_next_project,
        "vue": write_vue_project,
        "html": write_html_project,
        "go": write_go_project,
        "rust": write_rust_project,
        "java": write_java_project,
        "typescript": write_typescript_project,
        "angular": write_html_project,
        "generic": write_generic_project,
    }
    writer = writers.get(resolved, write_generic_project)
    return writer(root, name)


def write_node_project(root: Path, name: str) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    package = {
        "name": name,
        "version": "1.0.0",
        "private": True,
        "main": "index.js",
        "scripts": {"start": "node index.js"},
    }
    written.extend(_write_if_missing(root / "package.json", json.dumps(package, indent=2) + "\n"))
    written.extend(_write_if_missing(root / "index.js", f'console.log("Hello from {name}");\n'))
    written.extend(_write_if_missing(root / ".gitignore", "node_modules/\n.DS_Store\n"))
    return written


def write_python_project(root: Path, name: str) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    written.extend(
        _write_if_missing(
            root / "main.py",
            f'def main():\n    print("Hello from {name}")\n\n\nif __name__ == "__main__":\n    main()\n',
        )
    )
    written.extend(_write_if_missing(root / "requirements.txt", ""))
    written.extend(_write_if_missing(root / ".gitignore", "__pycache__/\n.venv/\n.DS_Store\n"))
    return written


def write_react_project(root: Path, name: str) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    src = root / "src"
    src.mkdir(exist_ok=True)
    written: list[str] = []
    package = {
        "name": name,
        "version": "1.0.0",
        "private": True,
        "type": "module",
        "scripts": {"dev": "vite", "build": "vite build"},
        "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
        "devDependencies": {"vite": "^5.4.0", "@vitejs/plugin-react": "^4.3.0"},
    }
    written.extend(_write_if_missing(root / "package.json", json.dumps(package, indent=2) + "\n"))
    written.extend(
        _write_if_missing(
            root / "index.html",
            f'<!doctype html>\n<html lang="en">\n<head><meta charset="UTF-8"><title>{name}</title></head>\n'
            '<body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body>\n</html>\n',
        )
    )
    written.extend(
        _write_if_missing(
            src / "main.jsx",
            'import { createRoot } from "react-dom/client";\n'
            'import App from "./App.jsx";\n'
            'createRoot(document.getElementById("root")).render(<App />);\n',
        )
    )
    written.extend(
        _write_if_missing(
            src / "App.jsx",
            f'export default function App() {{\n  return <h1>Hello from {name}</h1>;\n}}\n',
        )
    )
    written.extend(_write_if_missing(root / ".gitignore", "node_modules/\ndist/\n.DS_Store\n"))
    return written


def write_next_project(root: Path, name: str) -> list[str]:
    app = root / "app"
    app.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    package = {
        "name": name,
        "version": "1.0.0",
        "private": True,
        "scripts": {"dev": "next dev", "build": "next build", "start": "next start"},
        "dependencies": {"next": "^14.2.0", "react": "^18.3.1", "react-dom": "^18.3.1"},
    }
    written.extend(_write_if_missing(root / "package.json", json.dumps(package, indent=2) + "\n"))
    written.extend(
        _write_if_missing(
            app / "page.jsx",
            f'export default function Page() {{\n  return <h1>Hello from {name}</h1>;\n}}\n',
        )
    )
    written.extend(_write_if_missing(root / ".gitignore", "node_modules/\n.next/\n.DS_Store\n"))
    return written


def write_vue_project(root: Path, name: str) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    package = {
        "name": name,
        "version": "1.0.0",
        "private": True,
        "scripts": {"dev": "vite"},
        "dependencies": {"vue": "^3.5.0"},
    }
    written.extend(_write_if_missing(root / "package.json", json.dumps(package, indent=2) + "\n"))
    written.extend(
        _write_if_missing(
            root / "index.html",
            f'<!doctype html>\n<html><head><meta charset="UTF-8"><title>{name}</title></head>'
            f"<body><div id='app'>Hello from {name}</div></body></html>\n",
        )
    )
    written.extend(_write_if_missing(root / ".gitignore", "node_modules/\n.DS_Store\n"))
    return written


def write_html_project(root: Path, name: str) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    written.extend(
        _write_if_missing(
            root / "index.html",
            f'<!doctype html>\n<html lang="en">\n<head><meta charset="UTF-8"><title>{name}</title>'
            f'<link rel="stylesheet" href="styles.css"></head>\n<body>\n  <h1>Hello from {name}</h1>\n'
            '  <script src="app.js"></script>\n</body>\n</html>\n',
        )
    )
    written.extend(_write_if_missing(root / "styles.css", "body { font-family: sans-serif; }\n"))
    written.extend(_write_if_missing(root / "app.js", f'console.log("Hello from {name}");\n'))
    return written


def write_go_project(root: Path, name: str) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    written.extend(_write_if_missing(root / "go.mod", f"module {name}\n\ngo 1.22\n"))
    written.extend(
        _write_if_missing(
            root / "main.go",
            f'package main\n\nimport "fmt"\n\nfunc main() {{\n\tfmt.Println("Hello from {name}")\n}}\n',
        )
    )
    return written


def write_rust_project(root: Path, name: str) -> list[str]:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    written.extend(
        _write_if_missing(
            root / "Cargo.toml",
            f'[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2021"\n',
        )
    )
    written.extend(
        _write_if_missing(src / "main.rs", f'fn main() {{\n    println!("Hello from {name}");\n}}\n')
    )
    written.extend(_write_if_missing(root / ".gitignore", "/target\n"))
    return written


def write_java_project(root: Path, name: str) -> list[str]:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    class_name = "".join(part[:1].upper() + part[1:] for part in name.replace("-", "_").split("_") if part)
    class_name = class_name or "App"
    if class_name[0].isdigit():
        class_name = "App"
    written: list[str] = []
    written.extend(
        _write_if_missing(
            src / f"{class_name}.java",
            f'public class {class_name} {{\n    public static void main(String[] args) {{\n'
            f'        System.out.println("Hello from {name}");\n    }}\n}}\n',
        )
    )
    return written


def write_typescript_project(root: Path, name: str) -> list[str]:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    package = {
        "name": name,
        "version": "1.0.0",
        "private": True,
        "scripts": {"start": "npx tsx src/index.ts"},
    }
    written.extend(_write_if_missing(root / "package.json", json.dumps(package, indent=2) + "\n"))
    written.extend(_write_if_missing(root / "tsconfig.json", '{\n  "compilerOptions": { "strict": true }\n}\n'))
    written.extend(_write_if_missing(src / "index.ts", f'console.log("Hello from {name}");\n'))
    written.extend(_write_if_missing(root / ".gitignore", "node_modules/\n.DS_Store\n"))
    return written


def write_generic_project(root: Path, name: str) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    written.extend(
        _write_if_missing(
            root / "README.md",
            f"# {name}\n\nStarter folder created by Jarvis.\n",
        )
    )
    return written


def _write_if_missing(path: Path, content: str) -> list[str]:
    if path.exists():
        return []
    path.write_text(content, encoding="utf-8")
    return [path.name]
