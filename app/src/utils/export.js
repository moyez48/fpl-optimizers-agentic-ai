export function exportCSV(managerOutput) {
  const { selectedXI, bench, captain, viceCaptain } = managerOutput

  const getRole = (player) => {
    if (player.id === captain.id) return 'captain'
    if (player.id === viceCaptain.id) return 'vice-captain'
    if (selectedXI.find(p => p.id === player.id)) return 'starter'
    return 'bench'
  }

  const allPlayers = [...selectedXI, ...bench]
  const headers = ['name','position','team','price','xPts','adjustedXPts','xG','xA','fixtureDifficulty','nextFixture','injured','ownership','role']

  const rows = allPlayers.map(p => [
    p.name, p.position, p.team, p.price ?? '',
    p.xPts ?? '', p.adjustedXPts ?? '',
    p.xG ?? '', p.xA ?? '',
    p.fixtureDifficulty ?? '', p.nextFixture ?? '',
    p.injured ? 'true' : 'false',
    p.ownership ?? '',
    getRole(p),
  ])

  const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
  downloadFile(csv, 'fpl-optimizer-gw.csv', 'text/csv')
}

export function exportJSON(summary) {
  const json = JSON.stringify(summary, null, 2)
  downloadFile(json, 'fpl-optimizer-gw.json', 'application/json')
}

function downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
