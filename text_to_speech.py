"""Text to Speech Studio - Professional CLI & Automation Interface.

Convert text to speech, generate synchronized subtitles (.srt / .vtt),
produce multi-speaker dialogue master tracks, apply studio presets,
and batch-process documents using Microsoft Edge's Neural Voices.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from tts_engine import (
    BUILTIN_PRESETS,
    DEFAULT_VOICE,
    TTSStudioEngine,
)

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Optional rich formatting for ultra-sleek Gen-Z CLI output
try:
    from rich import print as rprint
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None


def print_banner() -> None:
    """Display modern CLI banner."""
    banner_text = (
        "[bold cyan]Text to Speech Studio[/bold cyan] [magenta]v2.0[/magenta] - "
        "[dim]Neural TTS • Subtitles • Multi-Speaker • Studio Presets[/dim]"
    )
    if HAS_RICH:
        console.print(Panel(banner_text, border_style="bright_blue"))
    else:
        print("=" * 65)
        print("Text to Speech Studio v2.0 - Neural TTS & Dialogue Studio")
        print("=" * 65)


def print_presets(engine: TTSStudioEngine) -> None:
    """Print available audio presets in a clean table."""
    presets = engine.get_all_presets()
    if HAS_RICH:
        table = Table(title="Studio Audio Presets", header_style="bold magenta")
        table.add_column("Preset ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="bold white")
        table.add_column("Voice", style="green")
        table.add_column("Speed", style="yellow")
        table.add_column("Pitch", style="yellow")
        table.add_column("Description", style="dim")

        for pid, data in sorted(presets.items()):
            table.add_row(
                pid,
                data.get("name", pid),
                data.get("voice", ""),
                data.get("rate", "+0%"),
                data.get("pitch", "+0Hz"),
                data.get("description", ""),
            )
        console.print(table)
    else:
        print("\nAvailable Studio Presets:")
        print("-" * 65)
        for pid, data in sorted(presets.items()):
            print(f"• {pid:15s} | {data.get('name', pid):25s} | Voice: {data.get('voice')} ({data.get('rate')})")
            print(f"  {data.get('description')}")
        print("-" * 65)


async def print_voices(
    engine: TTSStudioEngine,
    locale: Optional[str] = None,
    gender: Optional[str] = None,
    search: Optional[str] = None,
) -> None:
    """Print filtered neural voices."""
    voices = await engine.filter_voices(locale=locale, gender=gender, search_query=search)

    if HAS_RICH:
        table = Table(
            title=f"Neural Voices Directory ({len(voices)} available)",
            header_style="bold cyan",
        )
        table.add_column("Voice ID / ShortName", style="bold green")
        table.add_column("Locale", style="yellow")
        table.add_column("Gender", style="magenta")
        table.add_column("Friendly Name", style="white")

        for v in voices[:100]:  # limit display to first 100 for readability
            table.add_row(
                v.get("ShortName", ""),
                v.get("Locale", ""),
                v.get("Gender", ""),
                v.get("FriendlyName", ""),
            )
        console.print(table)
        if len(voices) > 100:
            console.print(f"[dim]... and {len(voices) - 100} more voices. Use --search or --locale to refine.[/dim]")
    else:
        print(f"\nAvailable Voices ({len(voices)} matching):")
        print("-" * 65)
        for v in voices[:100]:
            print(f"{v.get('ShortName'):35s} ({v.get('Locale')}, {v.get('Gender')}): {v.get('FriendlyName')}")
        if len(voices) > 100:
            print(f"... and {len(voices) - 100} more. Filter with --locale or --search.")
        print("-" * 65)


async def audition_voice(engine: TTSStudioEngine, voice: str, output: str = "sample.mp3") -> None:
    """Generate and notify user of a voice sample."""
    sample_text = (
        "Hello! This is a high-definition neural voice demonstration from Text to Speech Studio. "
        "Every word is rendered with natural human inflection."
    )
    if HAS_RICH:
        console.print(f"[bold cyan]Auditioning voice:[/bold cyan] [bold green]{voice}[/bold green]...")
    else:
        print(f"Auditioning voice: {voice}...")

    res = await engine.synthesize(sample_text, voice=voice, output_path=output)
    if HAS_RICH:
        console.print(f"[bold green]✓[/bold green] Sample saved to [yellow]{res.audio_path}[/yellow]")
    else:
        print(f"✓ Sample saved to {res.audio_path}")


def load_input_text(text: Optional[str], file_path: Optional[str]) -> str:
    """Retrieve text from argument or file."""
    if text and file_path:
        sys.exit("Error: provide either text or --file, not both.")
    if file_path:
        p = Path(file_path)
        if not p.exists():
            sys.exit(f"Error: file not found: {file_path}")
        try:
            return p.read_text(encoding="utf-8").strip()
        except OSError as exc:
            sys.exit(f"Error reading file {file_path}: {exc}")
    if not text:
        sys.exit("Error: provide text to convert (via arguments or --file). Run with --help for options.")
    return text.strip()


async def process_batch(
    engine: TTSStudioEngine,
    batch_pattern: str,
    output_dir: str,
    voice: str,
    rate: str,
    pitch: str,
    volume: str,
    generate_subtitles: bool,
) -> None:
    """Batch synthesize multiple text files."""
    files = glob.glob(batch_pattern)
    if not files:
        sys.exit(f"Error: no files matched batch pattern {batch_pattern!r}")

    out_directory = Path(output_dir)
    out_directory.mkdir(parents=True, exist_ok=True)

    if HAS_RICH:
        console.print(f"[bold cyan]Found {len(files)} files to process in batch.[/bold cyan]")
    else:
        print(f"Found {len(files)} files to process in batch.")

    for idx, fpath in enumerate(files, 1):
        file_p = Path(fpath)
        try:
            text = file_p.read_text(encoding="utf-8").strip()
            if not text:
                continue
            out_file = out_directory / f"{file_p.stem}.mp3"
            if HAS_RICH:
                console.print(f"[{idx}/{len(files)}] Processing [white]{file_p.name}[/white] -> [yellow]{out_file.name}[/yellow]")
            else:
                print(f"[{idx}/{len(files)}] Processing {file_p.name} -> {out_file.name}")

            await engine.synthesize(
                text=text,
                voice=voice,
                output_path=str(out_file),
                rate=rate,
                pitch=pitch,
                volume=volume,
                generate_subtitles=generate_subtitles,
            )
        except Exception as exc:
            print(f"Error processing {fpath}: {exc}", file=sys.stderr)

    if HAS_RICH:
        console.print(f"[bold green]✓ Batch synthesis completed! Files saved in {out_directory}[/bold green]")
    else:
        print(f"✓ Batch synthesis completed! Files saved in {out_directory}")


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Text to Speech Studio - Professional Neural Speech & Subtitle Studio (Microsoft Edge Neural Voices).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Basic synthesis
  python text_to_speech.py "Hello, welcome to my video!"

  # Apply a studio preset (TikTok, Podcast, Trailer, etc.)
  python text_to_speech.py --file script.txt --preset tiktok --srt

  # Multi-speaker dialogue script synthesis with subtitles
  python text_to_speech.py --dialogue sample_dialogue.txt --output master_dialogue.mp3

  # Batch convert all text files in a folder
  python text_to_speech.py --batch "docs/*.txt" --output-dir audio_output/

  # Search voices & audition
  python text_to_speech.py --list-voices --locale en-US --gender Female
  python text_to_speech.py --sample --voice en-US-AvaNeural
""",
    )

    parser.add_argument("text", nargs="?", help="Text to convert into speech.")
    parser.add_argument("-f", "--file", help="Path to input UTF-8 text or markdown file.")
    parser.add_argument("-o", "--output", default=None, help="Output MP3 file path (default: auto-generated from text).")
    parser.add_argument("-v", "--voice", default=DEFAULT_VOICE, help=f"Voice to use (default: {DEFAULT_VOICE}).")
    parser.add_argument("-r", "--rate", default="+0%", help="Speaking speed modifier, e.g. +15%%, -10%% (default: +0%%).")
    parser.add_argument("-p", "--pitch", default="+0Hz", help="Pitch shift, e.g. +20Hz, -15Hz (default: +0Hz).")
    parser.add_argument("--volume", default="+0%", help="Volume modifier, e.g. +20%%, -10%% (default: +0%%).")
    parser.add_argument("--provider", choices=["edge", "echon"], default=None, help="TTS provider engine (choices: edge, echon).")
    parser.add_argument("--preset", help="Apply a studio audio preset (e.g. echon, tiktok, podcast, trailer, storyteller, calm_asmr).")
    parser.add_argument("--list-presets", action="store_true", help="List all built-in and custom presets.")
    parser.add_argument("--srt", action="store_true", help="Generate synchronized SubRip (.srt) subtitle file.")
    parser.add_argument("--vtt", action="store_true", help="Generate synchronized WebVTT (.vtt) subtitle file.")
    parser.add_argument("-d", "--dialogue", help="Path to multi-speaker dialogue script file.")
    parser.add_argument("--batch", help="Glob pattern for batch processing text files (e.g. 'scripts/*.txt').")
    parser.add_argument("--output-dir", default="batch_output", help="Directory for batch outputs (default: batch_output).")
    parser.add_argument("--list-voices", action="store_true", help="List available neural voices.")
    parser.add_argument("--locale", help="Filter voices by locale (e.g. en-US, es-ES, ja-JP).")
    parser.add_argument("--gender", choices=["Male", "Female"], help="Filter voices by gender.")
    parser.add_argument("--search", help="Search voices by keyword, name, or country.")
    parser.add_argument("--sample", action="store_true", help="Audition a voice sample audio clip.")
    parser.add_argument("--stats", action="store_true", help="Analyze text metrics (words, duration, reading level) and exit.")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format for automation pipelines.")

    args = parser.parse_args()
    engine = TTSStudioEngine()

    # 1. Preset listing
    if args.list_presets:
        print_banner()
        print_presets(engine)
        return

    # 2. Voice listing
    if args.list_voices:
        print_banner()
        asyncio.run(print_voices(engine, locale=args.locale, gender=args.gender, search=args.search))
        return

    # 3. Voice audition sample
    if args.sample:
        print_banner()
        asyncio.run(audition_voice(engine, voice=args.voice, output=args.output or f"sample_{args.voice}.mp3"))
        return

    # Provider and voice resolution
    if getattr(args, "provider", None) == "echon":
        args.voice = "echon-narrator"

    voice = args.voice
    rate = args.rate
    pitch = args.pitch
    volume = args.volume

    if args.preset:
        presets = engine.get_all_presets()
        if args.preset not in presets:
            sys.exit(f"Error: Unknown preset {args.preset!r}. Run with --list-presets to see available options.")
        p = presets[args.preset]
        voice = p.get("voice", voice)
        rate = p.get("rate", rate)
        pitch = p.get("pitch", pitch)
        volume = p.get("volume", volume)
        if not args.json:
            print(f"Applied preset: {p.get('name', args.preset)} (Voice: {voice}, Rate: {rate}, Pitch: {pitch})")

    # 4. Batch mode
    if args.batch:
        print_banner()
        asyncio.run(
            process_batch(
                engine=engine,
                batch_pattern=args.batch,
                output_dir=args.output_dir,
                voice=voice,
                rate=rate,
                pitch=pitch,
                volume=volume,
                generate_subtitles=bool(args.srt or args.vtt),
            )
        )
        return

    # 5. Dialogue script mode
    if args.dialogue:
        if not args.json:
            print_banner()
        script_path = Path(args.dialogue)
        if not script_path.exists():
            sys.exit(f"Error: dialogue file not found: {args.dialogue}")
        script_text = script_path.read_text(encoding="utf-8")

        def dialogue_prog(msg: str) -> None:
            if not args.json:
                print(f"• {msg}")

        try:
            res = asyncio.run(
                engine.synthesize_dialogue(
                    script_text=script_text,
                    output_path=args.output,
                    generate_subtitles=bool(args.srt or args.vtt or True),
                    progress_cb=dialogue_prog,
                )
            )
            if args.json:
                print(
                    json.dumps(
                        {
                            "success": True,
                            "mode": "dialogue",
                            "audio_path": res.audio_path,
                            "duration_sec": res.duration_estimate_sec,
                            "word_count": res.word_count,
                            "srt_path": res.srt_path,
                            "vtt_path": res.vtt_path,
                        },
                        indent=2,
                    )
                )
            else:
                if HAS_RICH:
                    console.print(
                        Panel(
                            f"[bold green]✓ Master Dialogue Track Generated Successfully![/bold green]\n\n"
                            f"[cyan]Audio File:[/cyan] [yellow]{res.audio_path}[/yellow]\n"
                            f"[cyan]Duration:[/cyan] ~{res.duration_estimate_sec}s | [cyan]Words:[/cyan] {res.word_count}\n"
                            f"[cyan]Subtitles (SRT):[/cyan] {res.srt_path or 'None'}\n"
                            f"[cyan]Subtitles (VTT):[/cyan] {res.vtt_path or 'None'}",
                            title="Dialogue Studio Complete",
                            border_style="green",
                        )
                    )
                else:
                    print(f"\n✓ Master dialogue generated: {res.audio_path}")
                    print(f"  Duration: ~{res.duration_estimate_sec}s, Words: {res.word_count}")
                    if res.srt_path:
                        print(f"  Subtitles (SRT): {res.srt_path}")
        except Exception as exc:
            sys.exit(f"Error during dialogue synthesis: {exc}")
        return

    # 6. Single text mode
    input_text = load_input_text(args.text, args.file)

    # 7. Text stats only
    if args.stats:
        metrics = engine.analyze_text(input_text, rate)
        if args.json:
            print(json.dumps(metrics.__dict__, indent=2))
        elif HAS_RICH:
            table = Table(title="Text Analytics & Duration Estimate", header_style="bold cyan")
            table.add_column("Metric", style="bold white")
            table.add_column("Value", style="green")
            table.add_row("Characters", str(metrics.char_count))
            table.add_row("Characters (no spaces)", str(metrics.char_count_no_spaces))
            table.add_row("Words", str(metrics.word_count))
            table.add_row("Sentences", str(metrics.sentence_count))
            table.add_row("Estimated Audio Duration", f"{metrics.estimated_duration_seconds} seconds (~{round(metrics.estimated_duration_seconds/60, 1)} min)")
            table.add_row("Reading Complexity", metrics.reading_grade_level)
            console.print(table)
        else:
            print("\nText Analytics:")
            print(f"• Characters: {metrics.char_count} ({metrics.char_count_no_spaces} without spaces)")
            print(f"• Words:      {metrics.word_count}")
            print(f"• Sentences:  {metrics.sentence_count}")
            print(f"• Duration:   ~{metrics.estimated_duration_seconds}s")
            print(f"• Complexity: {metrics.reading_grade_level}")
        return

    # 8. Standard single synthesis
    if not args.json:
        print_banner()

    def prog_cb(msg: str) -> None:
        if not args.json:
            print(f"• {msg}")

    try:
        res = asyncio.run(
            engine.synthesize(
                text=input_text,
                voice=voice,
                output_path=args.output,
                rate=rate,
                pitch=pitch,
                volume=volume,
                generate_subtitles=bool(args.srt or args.vtt),
                progress_cb=prog_cb,
            )
        )
        if args.json:
            print(
                json.dumps(
                    {
                        "success": True,
                        "audio_path": res.audio_path,
                        "voice": res.voice,
                        "duration_sec": res.duration_estimate_sec,
                        "char_count": res.character_count,
                        "word_count": res.word_count,
                        "srt_path": res.srt_path,
                        "vtt_path": res.vtt_path,
                    },
                    indent=2,
                )
            )
        else:
            if HAS_RICH:
                console.print(
                    Panel(
                        f"[bold green]✓ Speech Synthesized Successfully![/bold green]\n\n"
                        f"[cyan]Audio Path:[/cyan] [yellow]{res.audio_path}[/yellow]\n"
                        f"[cyan]Voice:[/cyan] {res.voice} (Rate: {rate}, Pitch: {pitch})\n"
                        f"[cyan]Words:[/cyan] {res.word_count} | [cyan]Chars:[/cyan] {res.character_count} | [cyan]Est. Duration:[/cyan] ~{res.duration_estimate_sec}s\n"
                        + (f"[cyan]Subtitles (SRT):[/cyan] {res.srt_path}\n" if res.srt_path else "")
                        + (f"[cyan]Subtitles (VTT):[/cyan] {res.vtt_path}\n" if res.vtt_path else ""),
                        title="TTS Studio Generation Complete",
                        border_style="green",
                    )
                )
            else:
                print(f"\n✓ Generated speech saved to: {res.audio_path}")
                print(f"  Voice: {res.voice} | Words: {res.word_count} | Duration: ~{res.duration_estimate_sec}s")
                if res.srt_path:
                    print(f"  Subtitles (SRT): {res.srt_path}")
                if res.vtt_path:
                    print(f"  Subtitles (VTT): {res.vtt_path}")

    except Exception as exc:
        sys.exit(f"Error during speech synthesis: {exc}")


if __name__ == "__main__":
    main()
