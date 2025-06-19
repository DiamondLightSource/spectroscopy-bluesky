import json
import re
from pathlib import Path

import questionary
import typer
from jinja2 import DebugUndefined, Environment, FileSystemLoader, meta
from pydantic import BaseModel, Field

from spectroscopy_bluesky import __version__

app = typer.Typer(help="CLI for spectroscopy_bluesky utilities", add_completion=False)


class PlanParams(BaseModel):
    """
    Parameters for the PlanTemplate.
    """

    plan_name: str = Field(..., description="Name of the plan to be executed.")
    plan_args: dict = Field(default_factory=dict, description="Arguments for the plan.")
    plan_kwargs: dict = Field(
        default_factory=dict, description="Keyword arguments for the plan."
    )


def collect_user_inputs(template_vars: list[str]) -> dict[str, str]:
    typer.echo(f"📝 You need to provide values for {len(template_vars)} fields.\n")

    user_inputs = {}

    # Ask for beamline first
    beamline = questionary.text("📍 Please supply the beamline name").ask()
    if beamline is None:
        typer.secho("⚠️  Input cancelled. Exiting.", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    user_inputs["beamline"] = beamline

    # Ask for plan name next
    name = questionary.text("📍 Please supply the plan name").ask()
    if name is None:
        typer.secho("⚠️  Input cancelled. Exiting.", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    user_inputs["plan_name"] = beamline

    for i, var in enumerate(template_vars, 1):
        typer.secho(
            f"Step {i}/{len(template_vars)}: Provide value for '{var}'",
            fg=typer.colors.CYAN,
        )
        value = questionary.text(f"🔧 {var}").ask()
        if value is None:
            typer.secho("⚠️  Input cancelled. Exiting.", fg=typer.colors.YELLOW)
            raise typer.Exit(1)
        user_inputs[var] = value

    return user_inputs


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show the version and exit.",
        callback=lambda v: (print(__version__) or raise_(typer.Exit())) if v else None,
        is_eager=True,
    ),
):
    pass


@app.command()
def generate():
    """
    Interactively generate a plan template from Jinja2.
    """
    templates_dir = Path("./src/spectroscopy_bluesky/templates")
    if not templates_dir.exists():
        typer.secho(
            "❌ No templates directory found at ./templates", fg=typer.colors.RED
        )
        raise typer.Exit(1)

    template_files = list(templates_dir.glob("*.jinja2"))
    if not template_files:
        typer.secho("❌ No Jinja2 templates found in ./templates", fg=typer.colors.RED)
        raise typer.Exit(1)

    template_names = [f.stem for f in template_files]
    typer.echo("📦 Available templates:")
    for name in template_names:
        typer.echo(f" - {name}")

    template_choice = questionary.select(
        "📄 Which template do you want to use?", choices=template_names
    ).ask()

    if not template_choice:
        typer.secho("⚠️  No template selected. Exiting.", fg=typer.colors.YELLOW)
        raise typer.Exit(1)

    selected_template_file = f"{template_choice}.jinja2"

    # Setup Jinja environment
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)), undefined=DebugUndefined
    )
    template_source = env.loader.get_source(env, selected_template_file)[0]

    parsed_content = env.parse(template_source)
    vs = meta.find_undeclared_variables(parsed_content)
    template_vars = sorted(vs)

    user_inputs = collect_user_inputs(template_vars)

    INVALID_CHARS = r"[^a-zA-Z0-9_\-]"

    def safe_filename(name: str) -> str:
        return re.sub(INVALID_CHARS, "_", name)

    plan_name = safe_filename(user_inputs.get("plan_name", "unnamed_plan"))
    beamline = safe_filename(
        user_inputs.get("beamline", "unknown_beamline")
    )  # Validate core fields
    try:
        _ = PlanParams(
            plan_name=plan_name or "new_plan",
            plan_args=json.loads(user_inputs.get("plan_args", "{}")),
            plan_kwargs=json.loads(user_inputs.get("plan_kwargs", "{}")),
        )
    except Exception as e:
        typer.secho(f"❌ Validation failed: {e}", fg=typer.colors.RED)
        raise typer.Exit(1)

    rendered = env.get_template(selected_template_file).render(**user_inputs)

    output_path = (
        Path(f"./src/spectroscopy_bluesky/{beamline}") / "plans" / f"{plan_name}.py"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered)

    typer.secho(f"✅ Plan generated at {output_path}", fg=typer.colors.GREEN)
    typer.secho(
        "Now open 'docs/how-tos/bluesky_verbs.md' to preview how to build your plan further"
    )


def cli():
    app(prog_name="spectroscopy_bluesky")


def raise_(ex):
    raise ex


__all__ = ["cli"]
