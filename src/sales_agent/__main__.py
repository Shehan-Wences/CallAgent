from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path
import uvicorn
from .campaign import load_campaign, CampaignError
from .server import create_app

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sales_agent")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Run the voice agent server")
    serve.add_argument("--campaign", default=os.environ.get("CAMPAIGN", "campaigns/acmecrm.md"))
    serve.add_argument("--model", default=os.environ.get("MODEL", "gpt-realtime-mini"))
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args(argv)

    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
        return 2
    try:
        campaign = load_campaign(args.campaign)
    except CampaignError as e:
        print(f"ERROR loading campaign: {e}", file=sys.stderr)
        return 2

    campaign_path = Path(args.campaign)
    campaigns_dir = str(campaign_path.parent) if str(campaign_path.parent) != "." else "campaigns"
    app = create_app(campaign, args.model,
                     campaigns_dir=campaigns_dir,
                     default_campaign_file=campaign_path.name)
    print(f"Serving '{campaign.product.get('name')}' on http://localhost:{args.port} "
          f"(model={args.model})")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
