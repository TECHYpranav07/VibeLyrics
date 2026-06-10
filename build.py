"""
build.py — VibeLyrics Build Script

Automates packaging VibeLyrics into a standalone Windows executable.

Steps:
    1. Generates the app icon (.ico) using Pillow
    2. Installs build dependencies (PyInstaller, Pillow) if needed
    3. Runs PyInstaller to create the distributable
    4. Prints instructions for sharing

Usage:
    python build.py
"""

import subprocess
import sys
import os
import shutil
import io

# Force console output to UTF-8 encoding to prevent UnicodeEncodeError on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ──────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
ICON_PATH = os.path.join(ASSETS_DIR, "icon.ico")
DIST_DIR = os.path.join(PROJECT_DIR, "dist")
BUILD_DIR = os.path.join(PROJECT_DIR, "build")
OUTPUT_DIR = os.path.join(DIST_DIR, "VibeLyrics")

APP_NAME = "VibeLyrics"
APP_VERSION = "1.0.0"


# ──────────────────────────────────────────────────────────────
# Step 1: Install build dependencies
# ──────────────────────────────────────────────────────────────

def install_build_deps():
    """Install PyInstaller and Pillow if not already installed."""
    deps = ["pyinstaller", "Pillow"]
    for dep in deps:
        try:
            __import__(dep.lower().replace("-", "_"))
            print(f"  ✓ {dep} already installed")
        except ImportError:
            print(f"  ↓ Installing {dep}...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", dep],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"  ✓ {dep} installed")


# ──────────────────────────────────────────────────────────────
# Step 2: Generate .ico icon
# ──────────────────────────────────────────────────────────────

def generate_icon():
    """
    Generate a multi-resolution .ico file for the Windows executable.
    Creates a purple gradient circle with a white music note — same
    design as the programmatic icon in main.py, but as an .ico file.
    """
    from PIL import Image, ImageDraw, ImageFont

    os.makedirs(ASSETS_DIR, exist_ok=True)

    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = []

    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Background circle with gradient approximation
        # (PIL doesn't support gradients natively, so we draw concentric circles)
        cx, cy = size // 2, size // 2
        r = size // 2 - 1

        for i in range(r, 0, -1):
            # Gradient from purple (#7C3AED) to indigo (#4F46E5)
            t = i / r
            red = int(124 * t + 79 * (1 - t))
            green = int(58 * t + 70 * (1 - t))
            blue = int(237 * t + 229 * (1 - t))
            draw.ellipse(
                [cx - i, cy - i, cx + i, cy + i],
                fill=(red, green, blue, 255),
            )

        # Music note (♫) — draw with Unicode if font supports it,
        # otherwise draw simple shapes
        try:
            # Try to use a font that has music symbols
            font_size = int(size * 0.5)
            font = ImageFont.truetype("seguiemj.ttf", font_size)  # Segoe UI Emoji
            text = "♫"
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = (size - tw) // 2
            ty = (size - th) // 2 - bbox[1]
            draw.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)
        except Exception:
            # Fallback: draw simple music note shapes
            scale = size / 64.0
            # Note heads
            draw.ellipse(
                [int(14 * scale), int(36 * scale), int(30 * scale), int(48 * scale)],
                fill=(255, 255, 255, 255),
            )
            draw.ellipse(
                [int(34 * scale), int(32 * scale), int(50 * scale), int(44 * scale)],
                fill=(255, 255, 255, 255),
            )
            # Stems
            draw.rectangle(
                [int(28 * scale), int(14 * scale), int(31 * scale), int(44 * scale)],
                fill=(255, 255, 255, 255),
            )
            draw.rectangle(
                [int(48 * scale), int(10 * scale), int(51 * scale), int(40 * scale)],
                fill=(255, 255, 255, 255),
            )
            # Beam
            draw.rectangle(
                [int(28 * scale), int(12 * scale), int(51 * scale), int(16 * scale)],
                fill=(255, 255, 255, 255),
            )

        images.append(img)

    # Save as .ico with all sizes
    images[0].save(
        ICON_PATH,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print(f"  ✓ Icon generated: {ICON_PATH}")


# ──────────────────────────────────────────────────────────────
# Step 3: Run PyInstaller
# ──────────────────────────────────────────────────────────────

def run_pyinstaller():
    """Run PyInstaller to create the distributable."""

    # Clean previous builds
    for d in [BUILD_DIR, DIST_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"  ✓ Cleaned {os.path.basename(d)}/")

    # Determine icon argument
    icon_arg = f"--icon={ICON_PATH}" if os.path.exists(ICON_PATH) else ""

    # Build the PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconfirm",
        "--clean",
        "--windowed",              # No console window
        # Data files
        "--add-data", f"assets{os.pathsep}assets",
        # Hidden imports (PyInstaller might miss these)
        "--hidden-import", "winsdk",
        "--hidden-import", "winsdk.windows.media.control",
        "--hidden-import", "winsdk.windows.foundation",
        "--hidden-import", "keyboard",
        "--hidden-import", "requests",
        "--hidden-import", "concurrent.futures",
        # Exclude unnecessary modules to reduce size
        "--exclude-module", "matplotlib",
        "--exclude-module", "numpy",
        "--exclude-module", "pandas",
        "--exclude-module", "scipy",
        "--exclude-module", "tkinter",
        "--exclude-module", "unittest",
        "--exclude-module", "test",
        "--exclude-module", "PIL",  # Only needed for build, not runtime
        # Output
        "--distpath", DIST_DIR,
        "--workpath", BUILD_DIR,
        # Entry point
        "main.py",
    ]

    # Add icon if it exists
    if os.path.exists(ICON_PATH):
        cmd.insert(cmd.index("--noconfirm"), f"--icon={ICON_PATH}")

    print("\n  ⚙ Running PyInstaller (this may take 1-3 minutes)...\n")

    result = subprocess.run(
        cmd,
        cwd=PROJECT_DIR,
    )

    if result.returncode != 0:
        print("\n  ✗ Build FAILED! Check the output above for errors.")
        sys.exit(1)

    print(f"\n  ✓ Build complete!")


# ──────────────────────────────────────────────────────────────
# Step 4: Create ZIP for distribution
# ──────────────────────────────────────────────────────────────

def create_zip():
    """Create a ZIP file of the built application."""
    zip_name = f"{APP_NAME}_v{APP_VERSION}_Windows"
    zip_path = os.path.join(DIST_DIR, zip_name)

    if os.path.exists(OUTPUT_DIR):
        shutil.make_archive(zip_path, "zip", DIST_DIR, APP_NAME)
        final_zip = f"{zip_path}.zip"
        size_mb = os.path.getsize(final_zip) / (1024 * 1024)
        print(f"  ✓ ZIP created: {final_zip} ({size_mb:.1f} MB)")
        return final_zip
    else:
        print("  ⚠ Output directory not found, skipping ZIP creation")
        return None


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print(f"  🎵 {APP_NAME} Build Script v{APP_VERSION}")
    print("=" * 55)

    print("\n[1/4] Installing build dependencies...")
    install_build_deps()

    print("\n[2/4] Generating app icon...")
    generate_icon()

    print("\n[3/4] Building executable...")
    run_pyinstaller()

    print("\n[4/4] Creating distribution ZIP...")
    zip_path = create_zip()

    # Done!
    print("\n" + "=" * 55)
    print(f"  ✅ {APP_NAME} has been built successfully!")
    print("=" * 55)
    print(f"\n  📁 Executable: {OUTPUT_DIR}\\{APP_NAME}.exe")
    if zip_path:
        print(f"  📦 ZIP file:   {zip_path}")
    print(f"\n  To share with others:")
    print(f"    1. Send them the ZIP file")
    print(f"    2. They extract it and run {APP_NAME}.exe")
    print(f"    3. That's it! No Python needed. ✨")
    print()


if __name__ == "__main__":
    main()
