export const PLAYERS = [
  // ── GOALKEEPERS ─────────────────────────────────────────────────────
  { id: 1,  name: 'David Raya',           position: 'GKP', team: 'Arsenal',        price: 5.8,  form: 10, xPts: 7.6,  xG: 0.0, xA: 0.0, fixtureDifficulty: 3, nextFixture: 'Chelsea (A)',     injured: false, ownership: 26.5, variance: 2.1 },
  { id: 2,  name: 'Matz Sels',            position: 'GKP', team: 'Nottm Forest',   price: 4.8,  form: 9,  xPts: 6.8,  xG: 0.0, xA: 0.0, fixtureDifficulty: 2, nextFixture: 'Southampton (H)', injured: false, ownership: 18.7, variance: 2.0 },
  { id: 3,  name: 'Neto',                 position: 'GKP', team: 'Bournemouth',    price: 4.5,  form: 7,  xPts: 5.5,  xG: 0.0, xA: 0.0, fixtureDifficulty: 3, nextFixture: 'Brighton (A)',    injured: false, ownership: 4.2,  variance: 1.8 },
  { id: 4,  name: 'Jordan Pickford',      position: 'GKP', team: 'Everton',        price: 4.6,  form: 6,  xPts: 5.2,  xG: 0.0, xA: 0.0, fixtureDifficulty: 4, nextFixture: 'Man City (A)',    injured: false, ownership: 6.1,  variance: 1.9 },
  { id: 5,  name: 'Bart Verbruggen',      position: 'GKP', team: 'Brighton',       price: 4.4,  form: 8,  xPts: 6.0,  xG: 0.0, xA: 0.0, fixtureDifficulty: 3, nextFixture: 'Bournemouth (H)', injured: false, ownership: 7.3,  variance: 1.7 },
  { id: 6,  name: 'Aaron Ramsdale',       position: 'GKP', team: 'Southampton',    price: 4.0,  form: 4,  xPts: 3.8,  xG: 0.0, xA: 0.0, fixtureDifficulty: 2, nextFixture: 'Nottm Forest (A)', injured: false, ownership: 2.1, variance: 1.5 },

  // ── DEFENDERS ───────────────────────────────────────────────────────
  { id: 7,  name: 'Trent Alexander-Arnold', position: 'DEF', team: 'Liverpool',   price: 7.8,  form: 12, xPts: 9.5,  xG: 0.2, xA: 0.6, fixtureDifficulty: 2, nextFixture: 'Ipswich (H)',     injured: false, ownership: 44.0, variance: 3.0 },
  { id: 8,  name: 'Pedro Porro',           position: 'DEF', team: 'Spurs',        price: 6.2,  form: 11, xPts: 8.4,  xG: 0.1, xA: 0.4, fixtureDifficulty: 3, nextFixture: 'West Ham (H)',    injured: false, ownership: 19.3, variance: 2.8 },
  { id: 9,  name: 'Josko Gvardiol',        position: 'DEF', team: 'Man City',     price: 6.8,  form: 10, xPts: 8.0,  xG: 0.2, xA: 0.3, fixtureDifficulty: 2, nextFixture: 'Wolves (H)',      injured: false, ownership: 31.2, variance: 2.5 },
  { id: 10, name: 'Virgil van Dijk',       position: 'DEF', team: 'Liverpool',    price: 6.5,  form: 9,  xPts: 7.2,  xG: 0.15,xA: 0.1, fixtureDifficulty: 2, nextFixture: 'Ipswich (H)',     injured: false, ownership: 14.3, variance: 2.2 },
  { id: 11, name: 'Mykolenko',             position: 'DEF', team: 'Everton',      price: 4.5,  form: 5,  xPts: 3.1,  xG: 0.05,xA: 0.1, fixtureDifficulty: 4, nextFixture: 'Man City (A)',    injured: false, ownership: 3.4,  variance: 1.8 },
  { id: 12, name: 'Antonee Robinson',      position: 'DEF', team: 'Fulham',       price: 5.2,  form: 9,  xPts: 7.0,  xG: 0.1, xA: 0.3, fixtureDifficulty: 2, nextFixture: 'Everton (H)',     injured: false, ownership: 11.2, variance: 2.4 },
  { id: 13, name: 'Kieran Trippier',       position: 'DEF', team: 'Newcastle',    price: 7.0,  form: 7,  xPts: 5.8,  xG: 0.1, xA: 0.3, fixtureDifficulty: 2, nextFixture: 'Brentford (H)',   injured: true,  ownership: 22.1, variance: 2.6 },
  { id: 14, name: 'Ezri Konsa',            position: 'DEF', team: 'Aston Villa',  price: 5.5,  form: 8,  xPts: 6.5,  xG: 0.1, xA: 0.1, fixtureDifficulty: 3, nextFixture: 'Everton (A)',     injured: false, ownership: 9.8,  variance: 2.0 },
  { id: 15, name: 'Marc Guehi',            position: 'DEF', team: 'Crystal Palace', price: 4.5, form: 6, xPts: 5.0,  xG: 0.1, xA: 0.1, fixtureDifficulty: 3, nextFixture: 'Leicester (H)',   injured: false, ownership: 5.6,  variance: 1.9 },
  { id: 16, name: 'Kristoffer Ajer',       position: 'DEF', team: 'Brentford',    price: 4.8,  form: 7,  xPts: 5.5,  xG: 0.05,xA: 0.15,fixtureDifficulty: 2, nextFixture: 'Newcastle (A)',   injured: false, ownership: 4.1,  variance: 1.7 },
  { id: 17, name: 'Lino Sousa',            position: 'DEF', team: 'Leicester',    price: 4.2,  form: 4,  xPts: 3.5,  xG: 0.05,xA: 0.1, fixtureDifficulty: 3, nextFixture: 'C. Palace (A)',   injured: false, ownership: 2.3,  variance: 1.6 },

  // ── MIDFIELDERS ──────────────────────────────────────────────────────
  { id: 18, name: 'Mohamed Salah',         position: 'MID', team: 'Liverpool',    price: 13.2, form: 17, xPts: 13.8, xG: 0.8, xA: 0.5, fixtureDifficulty: 2, nextFixture: 'Ipswich (H)',     injured: false, ownership: 61.1, variance: 3.8 },
  { id: 19, name: 'Cole Palmer',           position: 'MID', team: 'Chelsea',      price: 11.4, form: 16, xPts: 12.5, xG: 0.6, xA: 0.5, fixtureDifficulty: 3, nextFixture: 'Arsenal (H)',     injured: false, ownership: 42.8, variance: 4.0 },
  { id: 20, name: 'Bukayo Saka',           position: 'MID', team: 'Arsenal',      price: 10.5, form: 14, xPts: 11.2, xG: 0.5, xA: 0.4, fixtureDifficulty: 3, nextFixture: 'Chelsea (A)',     injured: false, ownership: 38.2, variance: 3.2 },
  { id: 21, name: 'Bryan Mbeumo',          position: 'MID', team: 'Brentford',    price: 7.9,  form: 14, xPts: 10.1, xG: 0.5, xA: 0.3, fixtureDifficulty: 2, nextFixture: 'Newcastle (A)',   injured: false, ownership: 22.1, variance: 3.1 },
  { id: 22, name: 'Son Heung-min',         position: 'MID', team: 'Spurs',        price: 9.5,  form: 12, xPts: 9.8,  xG: 0.45,xA: 0.3, fixtureDifficulty: 3, nextFixture: 'West Ham (H)',    injured: false, ownership: 17.4, variance: 3.3 },
  { id: 23, name: 'Andreas Pereira',       position: 'MID', team: 'Fulham',       price: 6.0,  form: 11, xPts: 7.8,  xG: 0.3, xA: 0.3, fixtureDifficulty: 2, nextFixture: 'Everton (H)',     injured: false, ownership: 12.0, variance: 2.6 },
  { id: 24, name: 'Declan Rice',           position: 'MID', team: 'Arsenal',      price: 6.8,  form: 8,  xPts: 6.9,  xG: 0.15,xA: 0.2, fixtureDifficulty: 3, nextFixture: 'Chelsea (A)',     injured: true,  ownership: 11.4, variance: 2.4 },
  { id: 25, name: 'Antoine Semenyo',       position: 'MID', team: 'Bournemouth',  price: 5.8,  form: 10, xPts: 7.5,  xG: 0.3, xA: 0.3, fixtureDifficulty: 3, nextFixture: 'Brighton (A)',    injured: false, ownership: 7.1,  variance: 2.9 },
  { id: 26, name: 'Eberechi Eze',          position: 'MID', team: 'Crystal Palace', price: 6.5, form: 11, xPts: 8.2, xG: 0.35,xA: 0.25,fixtureDifficulty: 3, nextFixture: 'Leicester (H)',   injured: false, ownership: 13.5, variance: 2.8 },
  { id: 27, name: 'Bruno Fernandes',       position: 'MID', team: 'Man Utd',      price: 8.8,  form: 9,  xPts: 8.5,  xG: 0.4, xA: 0.35,fixtureDifficulty: 4, nextFixture: 'Man City (A)',    injured: false, ownership: 15.2, variance: 3.5 },
  { id: 28, name: 'Kaoru Mitoma',          position: 'MID', team: 'Brighton',     price: 6.8,  form: 10, xPts: 7.9,  xG: 0.35,xA: 0.3, fixtureDifficulty: 3, nextFixture: 'Bournemouth (H)', injured: false, ownership: 9.6,  variance: 2.7 },
  { id: 29, name: 'Jacob Ramsey',          position: 'MID', team: 'Aston Villa',  price: 5.8,  form: 9,  xPts: 7.1,  xG: 0.25,xA: 0.2, fixtureDifficulty: 3, nextFixture: 'Everton (A)',     injured: false, ownership: 6.8,  variance: 2.5 },
  { id: 30, name: 'Matheus Cunha',         position: 'MID', team: 'Wolves',       price: 7.4,  form: 12, xPts: 9.0,  xG: 0.4, xA: 0.3, fixtureDifficulty: 2, nextFixture: 'Man City (A)',    injured: false, ownership: 10.3, variance: 3.0 },
  { id: 31, name: 'Marcus Rashford',       position: 'MID', team: 'Man Utd',      price: 6.5,  form: 6,  xPts: 5.5,  xG: 0.25,xA: 0.15,fixtureDifficulty: 4, nextFixture: 'Man City (A)',    injured: true,  ownership: 8.7,  variance: 3.2 },
  { id: 32, name: 'Jarrod Bowen',          position: 'MID', team: 'West Ham',     price: 7.0,  form: 10, xPts: 8.0,  xG: 0.35,xA: 0.3, fixtureDifficulty: 3, nextFixture: 'Spurs (A)',       injured: false, ownership: 11.8, variance: 2.9 },
  { id: 33, name: 'Adam Armstrong',        position: 'MID', team: 'Southampton',  price: 5.0,  form: 5,  xPts: 4.2,  xG: 0.2, xA: 0.15,fixtureDifficulty: 2, nextFixture: 'Nottm Forest (A)', injured: false, ownership: 3.2, variance: 2.0 },

  // ── FORWARDS ─────────────────────────────────────────────────────────
  { id: 34, name: 'Erling Haaland',        position: 'FWD', team: 'Man City',     price: 14.0, form: 18, xPts: 14.2, xG: 1.1, xA: 0.2, fixtureDifficulty: 2, nextFixture: 'Wolves (H)',      injured: false, ownership: 72.4, variance: 4.1 },
  { id: 35, name: 'Alexander Isak',        position: 'FWD', team: 'Newcastle',    price: 9.2,  form: 15, xPts: 10.8, xG: 0.7, xA: 0.2, fixtureDifficulty: 2, nextFixture: 'Brentford (H)',   injured: false, ownership: 25.6, variance: 3.5 },
  { id: 36, name: 'Ollie Watkins',         position: 'FWD', team: 'Aston Villa',  price: 9.0,  form: 13, xPts: 10.2, xG: 0.6, xA: 0.3, fixtureDifficulty: 3, nextFixture: 'Everton (A)',     injured: false, ownership: 21.5, variance: 3.4 },
  { id: 37, name: 'Yoane Wissa',           position: 'FWD', team: 'Brentford',    price: 6.2,  form: 12, xPts: 8.9,  xG: 0.5, xA: 0.2, fixtureDifficulty: 2, nextFixture: 'Newcastle (A)',   injured: false, ownership: 9.7,  variance: 3.0 },
  { id: 38, name: 'Dominic Solanke',       position: 'FWD', team: 'Spurs',        price: 7.5,  form: 9,  xPts: 7.8,  xG: 0.4, xA: 0.2, fixtureDifficulty: 3, nextFixture: 'West Ham (H)',    injured: false, ownership: 6.8,  variance: 2.9 },
  { id: 39, name: 'Liam Delap',            position: 'FWD', team: 'Ipswich',      price: 5.9,  form: 8,  xPts: 6.2,  xG: 0.4, xA: 0.1, fixtureDifficulty: 3, nextFixture: 'Liverpool (A)',   injured: false, ownership: 8.4,  variance: 3.2 },
  { id: 40, name: 'Chris Wood',            position: 'FWD', team: 'Nottm Forest', price: 6.5,  form: 11, xPts: 8.5,  xG: 0.55,xA: 0.1, fixtureDifficulty: 2, nextFixture: 'Southampton (H)', injured: false, ownership: 12.3, variance: 2.8 },
  { id: 41, name: 'Raul Jimenez',          position: 'FWD', team: 'Fulham',       price: 6.0,  form: 8,  xPts: 6.8,  xG: 0.4, xA: 0.15,fixtureDifficulty: 2, nextFixture: 'Everton (H)',     injured: false, ownership: 5.9,  variance: 2.5 },
  { id: 42, name: 'Rasmus Hojlund',        position: 'FWD', team: 'Man Utd',      price: 7.2,  form: 8,  xPts: 7.0,  xG: 0.45,xA: 0.15,fixtureDifficulty: 4, nextFixture: 'Man City (A)',    injured: true,  ownership: 7.1,  variance: 3.3 },
  { id: 43, name: 'Evan Ferguson',         position: 'FWD', team: 'Brighton',     price: 5.5,  form: 7,  xPts: 6.0,  xG: 0.4, xA: 0.1, fixtureDifficulty: 3, nextFixture: 'Bournemouth (H)', injured: false, ownership: 4.8, variance: 2.6 },
  { id: 44, name: 'Dominic Calvert-Lewin', position: 'FWD', team: 'Everton',      price: 6.0,  form: 7,  xPts: 5.8,  xG: 0.35,xA: 0.1, fixtureDifficulty: 4, nextFixture: 'Man City (A)',    injured: false, ownership: 4.5,  variance: 2.7 },
  { id: 45, name: 'Jamie Vardy',           position: 'FWD', team: 'Leicester',    price: 5.0,  form: 5,  xPts: 4.5,  xG: 0.3, xA: 0.05,fixtureDifficulty: 3, nextFixture: 'C. Palace (A)',   injured: true,  ownership: 3.1,  variance: 2.4 },
  { id: 46, name: 'Mateus Cunha',          position: 'FWD', team: 'Wolves',       price: 5.8,  form: 9,  xPts: 7.2,  xG: 0.4, xA: 0.2, fixtureDifficulty: 2, nextFixture: 'Man City (A)',    injured: false, ownership: 6.7,  variance: 2.8 },
  { id: 47, name: 'Taiwo Awoniyi',         position: 'FWD', team: 'Nottm Forest', price: 5.5,  form: 7,  xPts: 6.0,  xG: 0.35,xA: 0.1, fixtureDifficulty: 2, nextFixture: 'Southampton (H)', injured: true,  ownership: 4.2, variance: 2.5 },
  { id: 48, name: 'Jean-Philippe Mateta',  position: 'FWD', team: 'Crystal Palace', price: 6.0, form: 9, xPts: 7.5,  xG: 0.45,xA: 0.15,fixtureDifficulty: 3, nextFixture: 'Leicester (H)',   injured: false, ownership: 7.3,  variance: 2.9 },
  { id: 49, name: 'Jarrod Freeman',        position: 'FWD', team: 'West Ham',     price: 5.2,  form: 6,  xPts: 5.0,  xG: 0.3, xA: 0.1, fixtureDifficulty: 3, nextFixture: 'Spurs (A)',       injured: false, ownership: 3.8,  variance: 2.2 },
  { id: 50, name: 'Cameron Archer',        position: 'FWD', team: 'Southampton',  price: 4.8,  form: 4,  xPts: 3.8,  xG: 0.2, xA: 0.05,fixtureDifficulty: 2, nextFixture: 'Nottm Forest (A)', injured: false, ownership: 2.5, variance: 2.0 },
]

// ── DEMO SQUAD (matches CLAUDE.md sample flow) ────────────────────────
// IDs mapped: Raya(1), Sels(2), A-Arnold(7), Porro(8), Gvardiol(9),
//             van Dijk(10), Mykolenko(11), Salah(18), Palmer(19),
//             Mbeumo(21), Rice(24), Pereira(23), Haaland(34),
//             Isak(35), Delap(39)
export const DEMO_SQUAD_IDS = [1, 2, 7, 8, 9, 10, 11, 18, 19, 21, 24, 23, 34, 35, 39]

export const getPlayerById = (id) => PLAYERS.find(p => p.id === id)
export const getPlayersByPosition = (pos) => PLAYERS.filter(p => p.position === pos)
