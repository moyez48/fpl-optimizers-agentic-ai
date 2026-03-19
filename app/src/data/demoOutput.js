// Static demo output — mirrors what the 3-agent pipeline would produce
// for the DEMO_SQUAD_IDS defined in players.js (GW25 scenario)

export const DEMO_STATS_OUTPUT = {
  rankedPlayers: [
    { id: 34, name: 'Erling Haaland',          position: 'FWD', team: 'Man City',   adjustedXPts: 14.2, xPts: 14.2, xG: 1.1, xA: 0.2, fixtureDifficulty: 2, nextFixture: 'Wolves (H)',    injured: false, form: 18, variance: 4.1, ownership: 72.4 },
    { id: 18, name: 'Mohamed Salah',            position: 'MID', team: 'Liverpool',  adjustedXPts: 13.8, xPts: 13.8, xG: 0.8, xA: 0.5, fixtureDifficulty: 2, nextFixture: 'Ipswich (H)',   injured: false, form: 17, variance: 3.8, ownership: 61.1 },
    { id: 19, name: 'Cole Palmer',              position: 'MID', team: 'Chelsea',    adjustedXPts: 12.5, xPts: 12.5, xG: 0.6, xA: 0.5, fixtureDifficulty: 3, nextFixture: 'Arsenal (H)',   injured: false, form: 16, variance: 4.0, ownership: 42.8 },
    { id: 35, name: 'Alexander Isak',           position: 'FWD', team: 'Newcastle',  adjustedXPts: 10.8, xPts: 10.8, xG: 0.7, xA: 0.2, fixtureDifficulty: 2, nextFixture: 'Brentford (H)', injured: false, form: 15, variance: 3.5, ownership: 25.6 },
    { id: 21, name: 'Bryan Mbeumo',             position: 'MID', team: 'Brentford',  adjustedXPts: 10.1, xPts: 10.1, xG: 0.5, xA: 0.3, fixtureDifficulty: 2, nextFixture: 'Newcastle (A)', injured: false, form: 14, variance: 3.1, ownership: 22.1 },
    { id: 7,  name: 'Trent Alexander-Arnold',   position: 'DEF', team: 'Liverpool',  adjustedXPts: 9.5,  xPts: 9.5,  xG: 0.2, xA: 0.6, fixtureDifficulty: 2, nextFixture: 'Ipswich (H)',   injured: false, form: 12, variance: 3.0, ownership: 44.0 },
    { id: 8,  name: 'Pedro Porro',              position: 'DEF', team: 'Spurs',      adjustedXPts: 8.4,  xPts: 8.4,  xG: 0.1, xA: 0.4, fixtureDifficulty: 3, nextFixture: 'West Ham (H)',  injured: false, form: 11, variance: 2.8, ownership: 19.3 },
    { id: 9,  name: 'Josko Gvardiol',           position: 'DEF', team: 'Man City',   adjustedXPts: 8.0,  xPts: 8.0,  xG: 0.2, xA: 0.3, fixtureDifficulty: 2, nextFixture: 'Wolves (H)',    injured: false, form: 10, variance: 2.5, ownership: 31.2 },
    { id: 23, name: 'Andreas Pereira',          position: 'MID', team: 'Fulham',     adjustedXPts: 7.8,  xPts: 7.8,  xG: 0.3, xA: 0.3, fixtureDifficulty: 2, nextFixture: 'Everton (H)',   injured: false, form: 11, variance: 2.6, ownership: 12.0 },
    { id: 1,  name: 'David Raya',               position: 'GKP', team: 'Arsenal',    adjustedXPts: 7.6,  xPts: 7.6,  xG: 0.0, xA: 0.0, fixtureDifficulty: 3, nextFixture: 'Chelsea (A)',   injured: false, form: 10, variance: 2.1, ownership: 26.5 },
    { id: 10, name: 'Virgil van Dijk',          position: 'DEF', team: 'Liverpool',  adjustedXPts: 7.2,  xPts: 7.2,  xG: 0.15,xA: 0.1, fixtureDifficulty: 2, nextFixture: 'Ipswich (H)',   injured: false, form: 9,  variance: 2.2, ownership: 14.3 },
    { id: 2,  name: 'Matz Sels',                position: 'GKP', team: 'Nottm Forest', adjustedXPts: 6.8, xPts: 6.8, xG: 0.0, xA: 0.0, fixtureDifficulty: 2, nextFixture: 'Southampton (H)', injured: false, form: 9, variance: 2.0, ownership: 18.7 },
    { id: 39, name: 'Liam Delap',               position: 'FWD', team: 'Ipswich',    adjustedXPts: 6.2,  xPts: 6.2,  xG: 0.4, xA: 0.1, fixtureDifficulty: 3, nextFixture: 'Liverpool (A)', injured: false, form: 8,  variance: 3.2, ownership: 8.4  },
    { id: 24, name: 'Declan Rice',              position: 'MID', team: 'Arsenal',    adjustedXPts: 4.6,  xPts: 6.9,  xG: 0.15,xA: 0.2, fixtureDifficulty: 3, nextFixture: 'Chelsea (A)',   injured: true,  form: 8,  variance: 2.4, ownership: 11.4 },
    { id: 11, name: 'Mykolenko',                position: 'DEF', team: 'Everton',    adjustedXPts: 3.1,  xPts: 3.1,  xG: 0.05,xA: 0.1, fixtureDifficulty: 4, nextFixture: 'Man City (A)',  injured: false, form: 5,  variance: 1.8, ownership: 3.4  },
  ],
  injuryAlerts: [
    { id: 24, name: 'Declan Rice', position: 'MID', team: 'Arsenal', adjustedXPts: 4.6 },
  ],
  squadTotalXPts: '101.3',
}

export const DEMO_MANAGER_OUTPUT = {
  selectedXI: [
    { id: 1,  name: 'David Raya',             position: 'GKP', team: 'Arsenal',   adjustedXPts: 7.6,  fixtureDifficulty: 3, nextFixture: 'Chelsea (A)',   injured: false },
    { id: 7,  name: 'Trent Alexander-Arnold', position: 'DEF', team: 'Liverpool', adjustedXPts: 9.5,  fixtureDifficulty: 2, nextFixture: 'Ipswich (H)',   injured: false },
    { id: 9,  name: 'Josko Gvardiol',         position: 'DEF', team: 'Man City',  adjustedXPts: 8.0,  fixtureDifficulty: 2, nextFixture: 'Wolves (H)',    injured: false },
    { id: 8,  name: 'Pedro Porro',            position: 'DEF', team: 'Spurs',     adjustedXPts: 8.4,  fixtureDifficulty: 3, nextFixture: 'West Ham (H)',  injured: false },
    { id: 10, name: 'Virgil van Dijk',        position: 'DEF', team: 'Liverpool', adjustedXPts: 7.2,  fixtureDifficulty: 2, nextFixture: 'Ipswich (H)',   injured: false },
    { id: 18, name: 'Mohamed Salah',          position: 'MID', team: 'Liverpool', adjustedXPts: 13.8, fixtureDifficulty: 2, nextFixture: 'Ipswich (H)',   injured: false },
    { id: 19, name: 'Cole Palmer',            position: 'MID', team: 'Chelsea',   adjustedXPts: 12.5, fixtureDifficulty: 3, nextFixture: 'Arsenal (H)',   injured: false },
    { id: 21, name: 'Bryan Mbeumo',           position: 'MID', team: 'Brentford', adjustedXPts: 10.1, fixtureDifficulty: 2, nextFixture: 'Newcastle (A)', injured: false },
    { id: 23, name: 'Andreas Pereira',        position: 'MID', team: 'Fulham',    adjustedXPts: 7.8,  fixtureDifficulty: 2, nextFixture: 'Everton (H)',   injured: false },
    { id: 34, name: 'Erling Haaland',         position: 'FWD', team: 'Man City',  adjustedXPts: 14.2, fixtureDifficulty: 2, nextFixture: 'Wolves (H)',    injured: false },
    { id: 35, name: 'Alexander Isak',         position: 'FWD', team: 'Newcastle', adjustedXPts: 10.8, fixtureDifficulty: 2, nextFixture: 'Brentford (H)', injured: false },
  ],
  bench: [
    { id: 2,  name: 'Matz Sels',    position: 'GKP', team: 'Nottm Forest', adjustedXPts: 6.8 },
    { id: 39, name: 'Liam Delap',   position: 'FWD', team: 'Ipswich',      adjustedXPts: 6.2 },
    { id: 24, name: 'Declan Rice',  position: 'MID', team: 'Arsenal',      adjustedXPts: 4.6, injured: true },
    { id: 11, name: 'Mykolenko',    position: 'DEF', team: 'Everton',      adjustedXPts: 3.1 },
  ],
  captain:    { id: 34, name: 'Erling Haaland', adjustedXPts: 14.2 },
  viceCaptain:{ id: 18, name: 'Mohamed Salah',  adjustedXPts: 13.8 },
  chipRecommendation: {
    chip: 'Triple Captain',
    target: 'Erling Haaland',
    reason: 'Haaland vs Wolves (H) — FDR 2, avg pts vs easy fixtures: 11.4',
    projectedGain: 28.4,
    confidence: 'HIGH',
  },
  formation: '4-4-2',
  totalProjectedPts: 121.8,
}

export const DEMO_TRANSFER_OUTPUT = {
  recommended: [
    {
      out: { id: 24, name: 'Declan Rice',  position: 'MID', price: 6.8, xPts: 4.6 },
      in:  { id: 21, name: 'Bryan Mbeumo', position: 'MID', price: 7.9, xPts: 10.1 },
      xPtsGain: 5.5,
      hitCost: 0,
      netGain: 5.5,
      priceDiff: -1.1,
      bankAfter: 1.2,
      isFreeTransfer: true,
      priority: 'HIGH',
    },
    {
      out: { id: 11, name: 'Mykolenko',       position: 'DEF', price: 4.5, xPts: 3.1 },
      in:  { id: 12, name: 'Antonee Robinson',position: 'DEF', price: 5.2, xPts: 7.0 },
      xPtsGain: 3.9,
      hitCost: 4,
      netGain: -0.1,
      priceDiff: -0.7,
      bankAfter: 0.5,
      isFreeTransfer: false,
      priority: 'LOW',
    },
  ],
  postTransferValue: 99.2,
  postTransferBank: 1.2,
  totalNetGain: '5.5',
}

export const DEMO_SUMMARY = {
  currentXPts: 101.3,
  optimizedXPts: 121.8,
  gainVsCurrent: 20.5,
  recommendedCaptain: 'Erling Haaland',
  chipUsed: 'Triple Captain',
  topTransfer: DEMO_TRANSFER_OUTPUT.recommended[0],
  squadValueAfter: 99.2,
  chartData: [
    { gw: 'GW22', actual: 62, projected: null },
    { gw: 'GW23', actual: 71, projected: null },
    { gw: 'GW24', actual: 58, projected: null },
    { gw: 'GW25', actual: null, projected: 121.8 },
  ],
}
