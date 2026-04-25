"""
core/artifact.py
Generates a self-contained, cinematic HTML report from scan results.
No server. No dependencies. Opens locally in the user's browser.
"""

import webbrowser
import tempfile
import os
from datetime import datetime
from typing import Dict, List, Optional


def generate(
    ghost_results: Optional[List[Dict]] = None,
    network_results: Optional[List[Dict]] = None,
    efficiency_results: Optional[Dict] = None,
    bucket: str = "N/A",
    region: str = "N/A",
    output_path: Optional[str] = None,
) -> str:
    """
    Renders scan data into a self-contained HTML artifact and returns the file path.
    Call open_in_browser(path) to display it.
    """

    ghost_results = ghost_results or []
    network_results = network_results or []

    # ── Derived totals ──────────────────────────────────────────────────────────
    ghost_count = len(ghost_results)
    ghost_size_gb = round(
        sum(r.get("size_bytes", 0) for r in ghost_results) / (1024**3), 3
    )
    ghost_cost = round(ghost_size_gb * 0.023, 2)

    network_leak_count = len([r for r in network_results if not r.get("has_endpoint")])
    network_cost_note = "$0.045 / GB via NAT" if network_leak_count > 0 else "$0.00"

    eff_waste = (
        round(efficiency_results.get("waste_ratio_pct", 0), 1)
        if efficiency_results
        else 0
    )
    eff_small_pct = (
        round(efficiency_results.get("small_file_pct", 0), 1)
        if efficiency_results
        else 0
    )
    eff_rec = (
        efficiency_results.get("recommendation", "N/A") if efficiency_results else "N/A"
    )

    total_issues = ghost_count + network_leak_count + (1 if eff_waste > 20 else 0)
    health_score = max(
        0, 100 - (ghost_count * 3) - (network_leak_count * 20) - int(eff_waste / 2)
    )

    scan_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    # ── Build ghost rows ────────────────────────────────────────────────────────
    ghost_rows = ""
    for r in ghost_results:
        size_kb = round(r.get("size_bytes", 0) / 1024, 1)
        age = r.get("age_days", "?")
        cost = r.get("monthly_cost", 0)
        key = r.get("key", "unknown")[:60]
        ghost_rows += f"""
        <tr>
          <td class="mono key-cell">{key}</td>
          <td class="mono center">{age}d</td>
          <td class="mono center">{size_kb} KB</td>
          <td class="mono center cost">${cost}/mo</td>
        </tr>"""

    if not ghost_rows:
        ghost_rows = (
            '<tr><td colspan="4" class="empty-row">✓ No ghost data found</td></tr>'
        )

    # ── Build network rows ──────────────────────────────────────────────────────
    network_rows = ""
    for r in network_results:
        vpc = r.get("vpc_id", "unknown")
        has_nat = "⚠ Present" if r.get("has_nat") else "—"
        has_ep = "✓ Yes" if r.get("has_endpoint") else "✗ Missing"
        ep_class = "good" if r.get("has_endpoint") else "bad"
        network_rows += f"""
        <tr>
          <td class="mono">{vpc}</td>
          <td class="mono center nat">{has_nat}</td>
          <td class="mono center {ep_class}">{has_ep}</td>
          <td class="mono center cost">{r.get("potential_saving", "—")}</td>
        </tr>"""

    if not network_rows:
        network_rows = '<tr><td colspan="4" class="empty-row">✓ All VPCs have S3 endpoints</td></tr>'

    # ── Score color ─────────────────────────────────────────────────────────────
    score_color = (
        "#00ff88"
        if health_score >= 80
        else "#ffcc00"
        if health_score >= 50
        else "#ff4444"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>S3 SWAT — Cost Audit Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:        #080808;
    --surface:   #0f0f0f;
    --border:    #1e1e1e;
    --border2:   #2a2a2a;
    --text:      #c8c8c8;
    --dim:       #555;
    --green:     #00ff88;
    --red:       #ff4444;
    --yellow:    #ffcc00;
    --cyan:      #00d4ff;
    --mono:      'JetBrains Mono', monospace;
    --sans:      'Syne', sans-serif;
  }}

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--mono);
    font-size: 13px;
    line-height: 1.6;
    min-height: 100vh;
    overflow-x: hidden;
  }}

  /* ── Scanline overlay ── */
  body::before {{
    content: '';
    position: fixed; inset: 0;
    background: repeating-linear-gradient(
      0deg,
      transparent,
      transparent 2px,
      rgba(0,0,0,0.03) 2px,
      rgba(0,0,0,0.03) 4px
    );
    pointer-events: none;
    z-index: 9999;
  }}

  /* ── Header ── */
  .header {{
    border-bottom: 1px solid var(--border2);
    padding: 28px 48px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky; top: 0;
    background: rgba(8,8,8,0.95);
    backdrop-filter: blur(12px);
    z-index: 100;
    animation: fadeDown 0.4s ease both;
  }}

  .logo {{
    font-family: var(--sans);
    font-size: 20px;
    font-weight: 800;
    letter-spacing: -0.5px;
    color: #fff;
  }}
  .logo span {{ color: var(--green); }}

  .meta {{
    font-size: 11px;
    color: var(--dim);
    text-align: right;
  }}
  .meta strong {{ color: var(--text); }}

  /* ── Health Score Hero ── */
  .hero {{
    padding: 64px 48px 48px;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 64px;
    align-items: center;
    animation: fadeUp 0.5s 0.1s ease both;
    border-bottom: 1px solid var(--border);
  }}

  .score-ring {{
    position: relative;
    width: 140px; height: 140px;
    flex-shrink: 0;
  }}
  .score-ring svg {{
    width: 140px; height: 140px;
    transform: rotate(-90deg);
  }}
  .score-ring .track {{
    fill: none;
    stroke: var(--border2);
    stroke-width: 6;
  }}
  .score-ring .arc {{
    fill: none;
    stroke: {score_color};
    stroke-width: 6;
    stroke-linecap: round;
    stroke-dasharray: 339.3;
    stroke-dashoffset: {339.3 * (1 - health_score / 100):.1f};
    filter: drop-shadow(0 0 6px {score_color});
    transition: stroke-dashoffset 1.2s cubic-bezier(0.16,1,0.3,1);
  }}
  .score-num {{
    position: absolute;
    inset: 0;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    font-family: var(--sans);
    font-size: 36px;
    font-weight: 800;
    color: {score_color};
    line-height: 1;
  }}
  .score-num small {{
    font-size: 11px;
    color: var(--dim);
    font-family: var(--mono);
    font-weight: 400;
    margin-top: 4px;
    letter-spacing: 1px;
  }}

  .hero-stats {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 24px;
  }}

  .stat-card {{
    border: 1px solid var(--border2);
    border-radius: 2px;
    padding: 20px 24px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.2s;
  }}
  .stat-card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
  }}
  .stat-card.red::before  {{ background: var(--red); }}
  .stat-card.yellow::before {{ background: var(--yellow); }}
  .stat-card.cyan::before {{ background: var(--cyan); }}

  .stat-label {{
    font-size: 10px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--dim);
    margin-bottom: 8px;
  }}
  .stat-value {{
    font-family: var(--sans);
    font-size: 28px;
    font-weight: 700;
    color: #fff;
    line-height: 1;
  }}
  .stat-sub {{
    font-size: 11px;
    color: var(--dim);
    margin-top: 6px;
  }}

  /* ── Sections ── */
  .sections {{ padding: 0 48px 64px; }}

  .section {{
    margin-top: 48px;
    animation: fadeUp 0.4s ease both;
  }}
  .section:nth-child(1) {{ animation-delay: 0.2s; }}
  .section:nth-child(2) {{ animation-delay: 0.3s; }}
  .section:nth-child(3) {{ animation-delay: 0.4s; }}

  .section-header {{
    display: flex;
    align-items: baseline;
    gap: 16px;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
  }}

  .scenario-tag {{
    font-size: 10px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--dim);
    font-family: var(--mono);
  }}

  .section-title {{
    font-family: var(--sans);
    font-size: 16px;
    font-weight: 700;
    color: #fff;
  }}

  .section-badge {{
    margin-left: auto;
    font-size: 11px;
    padding: 3px 10px;
    border-radius: 2px;
    font-family: var(--mono);
  }}
  .badge-red    {{ background: rgba(255,68,68,0.12); color: var(--red); border: 1px solid rgba(255,68,68,0.3); }}
  .badge-green  {{ background: rgba(0,255,136,0.08); color: var(--green); border: 1px solid rgba(0,255,136,0.2); }}
  .badge-yellow {{ background: rgba(255,204,0,0.10); color: var(--yellow); border: 1px solid rgba(255,204,0,0.25); }}

  /* ── Tables ── */
  .data-table {{
    width: 100%;
    border-collapse: collapse;
    border: 1px solid var(--border);
  }}
  .data-table th {{
    text-align: left;
    font-size: 10px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--dim);
    padding: 10px 16px;
    border-bottom: 1px solid var(--border2);
    background: var(--surface);
    font-weight: 400;
  }}
  .data-table td {{
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    vertical-align: middle;
  }}
  .data-table tr:last-child td {{ border-bottom: none; }}
  .data-table tr:hover td {{ background: rgba(255,255,255,0.02); }}

  .mono     {{ font-family: var(--mono); }}
  .center   {{ text-align: center; }}
  .key-cell {{ color: var(--cyan); font-size: 12px; max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .cost     {{ color: var(--red); }}
  .good     {{ color: var(--green); }}
  .bad      {{ color: var(--red); }}
  .nat      {{ color: var(--yellow); }}
  .empty-row {{ text-align: center; color: var(--green); padding: 20px; }}

  /* ── Efficiency panel ── */
  .eff-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }}

  .eff-block {{
    border: 1px solid var(--border2);
    padding: 20px 24px;
    border-radius: 2px;
  }}

  .eff-label {{
    font-size: 10px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--dim);
    margin-bottom: 8px;
  }}

  .eff-bar-wrap {{
    background: var(--border);
    border-radius: 2px;
    height: 6px;
    margin-top: 10px;
    overflow: hidden;
  }}

  .eff-bar {{
    height: 100%;
    border-radius: 2px;
    transition: width 1.4s cubic-bezier(0.16,1,0.3,1);
  }}

  .eff-value {{
    font-family: var(--sans);
    font-size: 32px;
    font-weight: 700;
    color: #fff;
    line-height: 1;
  }}

  /* ── Diff block ── */
  .diff-block {{
    background: var(--surface);
    border: 1px solid var(--border2);
    border-left: 3px solid var(--cyan);
    padding: 16px 20px;
    margin-top: 16px;
    font-size: 12px;
    line-height: 1.9;
  }}
  .diff-block .minus {{ color: var(--red); }}
  .diff-block .plus  {{ color: var(--green); }}
  .diff-block .neutral {{ color: var(--dim); }}

  /* ── Footer ── */
  .footer {{
    border-top: 1px solid var(--border);
    padding: 24px 48px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
    color: var(--dim);
  }}

  /* ── Animations ── */
  @keyframes fadeDown {{
    from {{ opacity: 0; transform: translateY(-8px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}
  @keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(12px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}
</style>
</head>
<body>

<!-- ── HEADER ────────────────────────────────────────────────── -->
<header class="header">
  <div class="logo">S3<span>SWAT</span></div>
  <div class="meta">
    <strong>Bucket:</strong> {bucket} &nbsp;·&nbsp;
    <strong>Region:</strong> {region} &nbsp;·&nbsp;
    {scan_time}
  </div>
</header>

<!-- ── HERO ──────────────────────────────────────────────────── -->
<section class="hero">
  <div class="score-ring">
    <svg viewBox="0 0 120 120">
      <circle class="track" cx="60" cy="60" r="54"/>
      <circle class="arc"   cx="60" cy="60" r="54"/>
    </svg>
    <div class="score-num">
      {health_score}
      <small>HEALTH</small>
    </div>
  </div>

  <div class="hero-stats">
    <div class="stat-card red">
      <div class="stat-label">Ghost Data Found</div>
      <div class="stat-value">{ghost_count}</div>
      <div class="stat-sub">{ghost_size_gb} GB invisible &amp; billed</div>
    </div>
    <div class="stat-card yellow">
      <div class="stat-label">Network Leaks</div>
      <div class="stat-value">{network_leak_count}</div>
      <div class="stat-sub">{network_cost_note}</div>
    </div>
    <div class="stat-card cyan">
      <div class="stat-label">Tiering Waste</div>
      <div class="stat-value">{eff_waste}%</div>
      <div class="stat-sub">{eff_small_pct}% of objects &lt; 128KB</div>
    </div>
  </div>
</section>

<!-- ── SECTIONS ──────────────────────────────────────────────── -->
<div class="sections">

  <!-- Scenario 1: Ghost Hunter -->
  <div class="section">
    <div class="section-header">
      <span class="scenario-tag">Scenario 01</span>
      <span class="section-title">Ghost Hunter — Incomplete Multipart Uploads</span>
      <span class="section-badge {"badge-red" if ghost_count > 0 else "badge-green"}">
        {"%d leak%s · $%.2f/mo" % (ghost_count, "s" if ghost_count != 1 else "", ghost_cost) if ghost_count > 0 else "Clean"}
      </span>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th>Object Key</th>
          <th style="text-align:center">Age</th>
          <th style="text-align:center">Size</th>
          <th style="text-align:center">Monthly Cost</th>
        </tr>
      </thead>
      <tbody>
        {ghost_rows}
      </tbody>
    </table>

    {'<div class="diff-block"><span class="minus">- versioning_policy: none (uploading forever)</span><br><span class="plus">+ lifecycle_policy: abort_incomplete_multipart_upload after 7 days</span><br><span class="neutral">  estimated_saving: $' + str(ghost_cost) + "/mo</span></div>" if ghost_count > 0 else ""}
  </div>

  <!-- Scenario 2: Network Scout -->
  <div class="section">
    <div class="section-header">
      <span class="scenario-tag">Scenario 02</span>
      <span class="section-title">Network Scout — VPC Endpoint Audit</span>
      <span class="section-badge {"badge-red" if network_leak_count > 0 else "badge-green"}">
        {"%d VPC missing S3 endpoint" % network_leak_count if network_leak_count > 0 else "Clean"}
      </span>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th>VPC ID</th>
          <th style="text-align:center">NAT Gateway</th>
          <th style="text-align:center">S3 Endpoint</th>
          <th style="text-align:center">Data Cost</th>
        </tr>
      </thead>
      <tbody>
        {network_rows}
      </tbody>
    </table>

    {'<div class="diff-block"><span class="minus">- s3_traffic_route: NAT Gateway ($0.045/GB processing)</span><br><span class="plus">+ s3_traffic_route: Gateway VPC Endpoint ($0.00)</span><br><span class="neutral">  action: aws ec2 create-vpc-endpoint --vpc-endpoint-type Gateway --service-name com.amazonaws.' + region + ".s3</span></div>" if network_leak_count > 0 else ""}
  </div>

  <!-- Scenario 3: Efficiency Audit -->
  <div class="section">
    <div class="section-header">
      <span class="scenario-tag">Scenario 03</span>
      <span class="section-title">Efficiency Audit — Small File 128KB Tax</span>
      <span class="section-badge {"badge-red" if eff_waste > 30 else "badge-yellow" if eff_waste > 10 else "badge-green"}">
        {eff_rec}
      </span>
    </div>

    <div class="eff-grid">
      <div class="eff-block">
        <div class="eff-label">Small Objects (&lt;128 KB)</div>
        <div class="eff-value">{eff_small_pct}%</div>
        <div class="eff-bar-wrap">
          <div class="eff-bar" id="small-bar" style="width:0%;background:{"var(--red)" if eff_small_pct > 50 else "var(--yellow)"};"></div>
        </div>
      </div>
      <div class="eff-block">
        <div class="eff-label">Billed-vs-Actual Bloat</div>
        <div class="eff-value">{eff_waste}%</div>
        <div class="eff-bar-wrap">
          <div class="eff-bar" id="waste-bar" style="width:0%;background:{"var(--red)" if eff_waste > 30 else "var(--yellow)"};"></div>
        </div>
      </div>
    </div>

    <div class="diff-block" style="margin-top:16px">
      <span class="neutral">  # Recommendation</span><br>
      {'<span class="minus">- tier: IntelligentTiering  # Will INCREASE cost for tiny files</span><br><span class="plus">+ tier: Standard           # Cheapest option when obj_size &lt; 128KB</span>' if eff_rec == "STAY IN STANDARD" else '<span class="plus">+ tier: IntelligentTiering  # Safe. Objects large enough to benefit from tier moves.</span>'}
    </div>
  </div>

</div><!-- /sections -->

<!-- ── FOOTER ─────────────────────────────────────────────────── -->
<footer class="footer">
  <span>Generated by <strong style="color:#fff">s3-swat</strong> CLI · Read-Only scan · No data was modified</span>
  <span>Total issues found: <strong style="color:{"var(--red)" if total_issues > 0 else "var(--green)"}">{total_issues}</strong></span>
</footer>

<script>
  // Animate bars after page load
  window.addEventListener('load', () => {{
    setTimeout(() => {{
      const small = document.getElementById('small-bar');
      const waste = document.getElementById('waste-bar');
      if (small) small.style.width = '{eff_small_pct}%';
      if (waste) waste.style.width = '{min(eff_waste, 100)}%';
    }}, 300);
  }});
</script>

</body>
</html>
"""

    # ── Write to file ────────────────────────────────────────────────────────────
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=".html", prefix="s3swat_report_"
        )
        output_path = tmp.name
        tmp.write(html.encode("utf-8"))
        tmp.close()
    else:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    return output_path


def open_in_browser(path: str) -> None:
    """Opens the generated artifact in the user's default browser."""
    webbrowser.open(f"file://{os.path.abspath(path)}")
