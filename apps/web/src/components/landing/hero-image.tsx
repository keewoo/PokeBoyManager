import Image from "next/image";

// Fournie par JF (mission `pbm-front-accueil`, point 0) en 1600×1066 : remplace le bloc de
// démonstration vide (neuf rectangles sans image, jamais implémentés) qui illustrait jusqu'ici
// la promesse du produit par du vide. `next/image` génère les variantes de taille et les formats
// modernes (AVIF/WebP) à partir de cette seule source — une largeur adaptée à chaque écran, sans
// dupliquer un second fichier à la main (`sizes` ci-dessous couvre aussi bien un téléphone à
// 390 px que la moitié d'un conteneur `max-w-6xl` en desktop).
export function HeroImage() {
  return (
    <figure className="m-0 overflow-hidden rounded-xl bg-screen shadow-lg">
      <Image
        src="/hero-1600.jpg"
        alt="Un dresseur photographie son classeur ; ses cartes prennent vie autour de lui et un duel s'affiche sur une tablette."
        width={1600}
        height={1066}
        priority
        sizes="(min-width: 1024px) 45vw, 100vw"
        className="h-auto w-full"
      />
    </figure>
  );
}
