// Pitch view — shows the starting XV in a 4-3-3 (or other) formation.
// Uses CSS grid with absolute-positioned player chips on a stylized pitch.

const POSITION_ROWS = ['FWD', 'MID', 'DEF', 'GKP']; // top → bottom

function PlayerChip({ player, isCaptain, isVice, onClick, theme }) {
  const team = TEAMS[player.team];
  return (
    <button className={`pchip pchip-${theme}`} onClick={onClick} type="button">
      <div className="pchip-shirt" style={{ '--team': team.primary }}>
        <div className="pchip-shirt-stripe" />
        {isCaptain && <span className="pchip-badge pchip-cap">C</span>}
        {isVice && <span className="pchip-badge pchip-vice">V</span>}
      </div>
      <div className="pchip-name">{player.name}</div>
      <div className="pchip-meta">
        <span>{team.short}</span>
        <span className="pchip-xp">{player.xp.toFixed(1)}</span>
      </div>
    </button>
  );
}

function PitchView({ squad, players, onPlayerClick, theme }) {
  const rows = POSITION_ROWS.map((pos) => {
    const ids = squad.starting[pos] || [];
    return { pos, players: ids.map((id) => players.find((p) => p.id === id)).filter(Boolean) };
  });

  return (
    <div className={`pitch pitch-${theme}`}>
      <div className="pitch-bg">
        <div className="pitch-circle" />
        <div className="pitch-line pitch-line-mid" />
        <div className="pitch-box pitch-box-top" />
        <div className="pitch-box pitch-box-bot" />
        <div className="pitch-arc pitch-arc-top" />
        <div className="pitch-arc pitch-arc-bot" />
      </div>
      <div className="pitch-rows">
        {rows.map((row) => (
          <div key={row.pos} className="pitch-row">
            {row.players.map((p) => (
              <PlayerChip
                key={p.id}
                player={p}
                isCaptain={p.id === squad.captain}
                isVice={p.id === squad.vice}
                onClick={() => onPlayerClick(p)}
                theme={theme}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function BenchView({ squad, players, onPlayerClick, theme }) {
  const benchPlayers = squad.bench.map((id) => players.find((p) => p.id === id)).filter(Boolean);
  return (
    <div className={`bench bench-${theme}`}>
      <div className="bench-label">Bench</div>
      <div className="bench-row">
        {benchPlayers.map((p, i) => (
          <div key={p.id} className="bench-slot">
            <span className="bench-num">{i + 1}</span>
            <PlayerChip player={p} onClick={() => onPlayerClick(p)} theme={theme} />
          </div>
        ))}
      </div>
    </div>
  );
}

window.PitchView = PitchView;
window.BenchView = BenchView;
window.PlayerChip = PlayerChip;
