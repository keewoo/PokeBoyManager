import { describe, expect, it } from "vitest";

import {
  TRADUCTEURS,
  TYPES_EVENEMENT_CONNUS,
  construireJournal,
  traduireEvenement,
  type CoupJournal,
} from "./journal";

const MOI = "alice";
const ADV = "bob";

/** Un événement de coup minimal. */
function evt(type: string, donnees: Record<string, unknown> = {}) {
  return { type, donnees };
}

describe("traduction des événements du journal", () => {
  it("rend une phrase française pour CHAQUE type d'événement connu (aucun type brut)", () => {
    // Des données plausibles par type, pour que chaque traducteur produise une vraie phrase.
    const donneesParType: Record<string, Record<string, unknown>> = {
      pioche_melangee: { joueur: MOI, taille: 60 },
      cartes_piochees: { joueur: MOI, nombre: 2, instance_ids: ["c-1", "c-2"] },
      phase_avancee: { de: "pioche", vers: "principale", numero: 1, joueur_actif: MOI },
      tour_commence: { numero: 2, joueur_actif: ADV },
      attaque_declaree: { joueur: MOI, degats: 0 },
      confusion_resolue: { joueur: MOI, etat: "confus", regle: "R-11.5", pile_ou_face: "pile", attaque_annulee: true, degats: 30 },
      degats: { cible: "p-7", degats: 120, compteurs: 12, detail: "60 base, ×2 faiblesse = 120", au_banc: false },
      partie_terminee: { vainqueur: MOI, raison: "abandon", abandon_par: ADV },
      retraite_effectuee: { joueur: MOI, ancien_actif: "p-1", nouvel_actif: "p-2", cout: 1, energies_defaussees: ["e-1"] },
      promotion_effectuee: { joueur: MOI, nouvel_actif: "p-3" },
      echange_force_effectue: { joueur: ADV, ancien_actif: "p-4", nouvel_actif: "p-5" },
      etat_checkup: { joueur: MOI, etat: "empoisonne", regle: "R-11.7", degats: 10, gueri: false },
      effet_expire: {},
      ko: { joueur: ADV, pokemon: "p-9", compteurs: 120, recompenses_prises: 1, par: MOI },
      promotion_requise: { joueur: MOI },
      pokemon_pose: { joueur: MOI, pokemon: "p-10", zone: "banc", ref: "base1-12" },
      evolution: { joueur: MOI, base: "p-10", vers: "ev1-5", nom: "Dracaufeu", etats_soignes: [] },
      // Mise en place et horloges (lots j-initialisation / j-coups-joueur / j-timer).
      energie_attachee: { joueur: MOI, energie: "e-1", ref: "base1-energy", cible: "p-1", fournit: { electrique: 1 } },
      placement_cache: { joueur: MOI },
      mulligan: { joueur: MOI, numero: 1, simultane: false, bonus_pour: ADV },
      main_revelee: { joueur: MOI, cartes: [{ instance_id: "c-1", ref: "base1-1" }] },
      mise_en_place_prete: { joueurs: [{ id: MOI, mulligans: 1, bonus: 0 }] },
      mise_en_place_revelee: { joueurs: [{ joueur: MOI, actif: "base1-1", banc: ["base1-2"], recompenses_nombre: 6, bonus_pioches: 0 }] },
      fin_tour: { joueur: MOI, de: "principale" },
      // Combat et effets de carte (lots j-attaque / effets de carte).
      cout_paye: { cout: { types: { electrique: 1 }, incolore: 0 }, detail: "Coût payé : ⚡ par énergie électrique", affectations: [] },
      effet_resolu: { source: { libelle: "Bandeau Musclé", ref: "tool-1", instance_id: "t-1" }, type_effet: "degats", regle: "R-10", libelle: "dégâts +20" },
      effet_sans_cible: { source: { libelle: "Gardevoir", ref: "ev2-7", instance_id: "p-20" }, type_effet: "soin", regle: "R-11", libelle: "soin", raison: "aucune cible valide" },
      verrou_pose: { nom: "attaque_interdite", portee: "ce_tour", source: { libelle: "Carte Piège" }, regle: "R-12", cible: null, pose_au_tour: 1 },
      verrou_leve: { nom: "attaque_interdite", portee: "ce_tour", source: { libelle: "Carte Piège" }, regle: "R-12", cible: null, au_tour: 2 },
      dsl_pile_ou_face: { pieces: 2, faces: 1 },
      dsl_cout_impayable: { source: { libelle: "Carte Effet" }, raison: "coût non payable" },
    };

    for (const type of TYPES_EVENEMENT_CONNUS) {
      const donnees = donneesParType[type];
      expect(donnees, `donnée de test manquante pour « ${type} »`).toBeDefined();
      const ligne = traduireEvenement(evt(type, donnees), 0, 0, MOI, MOI);
      expect(ligne.traduit, `« ${type} » doit être traduit`).toBe(true);
      expect(ligne.texte.length, `« ${type} » doit produire une phrase`).toBeGreaterThan(0);
      // Aucun identifiant technique brut ne doit rester dans la phrase.
      expect(ligne.texte).not.toContain(type);
    }
  });

  it("couvre exactement les clés du registre", () => {
    expect(new Set(TYPES_EVENEMENT_CONNUS)).toEqual(new Set(Object.keys(TRADUCTEURS)));
  });

  it("un type inconnu n'est jamais masqué : ligne traduit:false montrant l'identifiant brut", () => {
    const ligne = traduireEvenement(evt("effet_mysterieux", { joueur: MOI }), 0, 3, MOI, MOI);
    expect(ligne.traduit).toBe(false);
    expect(ligne.texte).toContain("effet_mysterieux");
  });

  it("classe le camp d'un coup joueur par donnees.joueur comparé au destinataire", () => {
    expect(traduireEvenement(evt("cartes_piochees", { joueur: MOI, nombre: 1 }), 0, 0, MOI, MOI).categorie).toBe("moi");
    expect(traduireEvenement(evt("cartes_piochees", { joueur: ADV, nombre: 1 }), 0, 0, MOI, ADV).categorie).toBe("adversaire");
  });

  it("classe les effets automatiques en « auto », quel que soit le joueur touché", () => {
    const poison = traduireEvenement(evt("etat_checkup", { joueur: MOI, etat: "empoisonne", degats: 10 }), 0, 0, MOI, MOI);
    expect(poison.categorie).toBe("auto");
    expect(poison.texte).toContain("Poison");
    expect(poison.texte).toContain("ton Actif");
  });

  it("expose le détail du calcul des dégâts et la cible à surligner", () => {
    const ligne = traduireEvenement(
      evt("degats", { cible: "p-7", degats: 90, compteurs: 9, detail: "60 base, ×2 faiblesse, −30 résistance = 90" }),
      0,
      0,
      MOI,
      MOI,
    );
    expect(ligne.detailDegats).toBe("60 base, ×2 faiblesse, −30 résistance = 90");
    expect(ligne.surligne).toBe("p-7");
    expect(ligne.texte).toContain("90");
  });

  it("ne révèle pas quelles cartes l'adversaire pioche (nombre seulement)", () => {
    const ligne = traduireEvenement(evt("cartes_piochees", { joueur: ADV, nombre: 3 }), 0, 0, MOI, ADV);
    expect(ligne.texte).toContain("3");
    expect(ligne.refs).toEqual([]);
  });
});

describe("construireJournal", () => {
  it("déduit le camp des dégâts depuis l'auteur du coup (les dégâts ne portent pas de joueur)", () => {
    // Un coup d'attaque : attaque_declaree (porte joueur) puis degats (porte la cible, pas le joueur).
    const coups: CoupJournal[] = [
      {
        numero: 0,
        evenements: [
          evt("attaque_declaree", { joueur: MOI, degats: 0 }),
          evt("degats", { cible: "p-7", degats: 50, compteurs: 5, detail: "50 base = 50" }),
        ],
      },
    ];
    const lignes = construireJournal(coups, MOI);
    expect(lignes).toHaveLength(2);
    expect(lignes.at(1)?.type).toBe("degats");
    // Sans joueur propre, les dégâts héritent du camp de l'auteur du coup (moi).
    expect(lignes.at(1)?.categorie).toBe("moi");
  });

  it("aplatit les coups dans l'ordre, une ligne par événement, clés stables", () => {
    const coups: CoupJournal[] = [
      { numero: 5, evenements: [evt("phase_avancee", { de: "pioche", vers: "principale", numero: 1 })] },
      { numero: 6, evenements: [evt("tour_commence", { numero: 2, joueur_actif: ADV })] },
    ];
    const lignes = construireJournal(coups, MOI);
    expect(lignes.map((l) => l.cle)).toEqual(["5-0", "6-0"]);
    expect(lignes.every((l) => l.traduit)).toBe(true);
  });
});
