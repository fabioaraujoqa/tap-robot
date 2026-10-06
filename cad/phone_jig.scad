// Gabarito (jig) para Moto G06 na mesa da P1S.
// ATENÇÃO: não foi renderizado/testado fisicamente. Imprima primeiro uma versão
// rápida (baixo infill) e confira o encaixe com o celular real antes de usar.
//
// Só os cantos seguram o celular: os lados ficam livres para os botões
// (liga/volume na lateral direita) e o cabo USB-C (parte inferior).

phone_w = 77.5;    // largura
phone_h = 171.35;  // altura
phone_t = 8.31;    // espessura
tol     = 0.4;     // folga por lado (ajuste conforme a sua impressora)

base_t   = 3;      // espessura da base
wall_h   = 4;      // altura dos cantos (menor que a espessura do celular)
wall_th  = 3;      // espessura da parede
corner_l = 24;     // comprimento do braço de cada canto
margin   = 8;      // sobra da base além das paredes

pocket_w = phone_w + 2*tol;
pocket_h = phone_h + 2*tol;
plate_w  = pocket_w + 2*(wall_th + margin);
plate_h  = pocket_h + 2*(wall_th + margin);
ox = (plate_w - pocket_w)/2;   // origem do "bolso" na base
oy = (plate_h - pocket_h)/2;

echo(str("Superfície da tela fica a ", base_t + phone_t, " mm acima da mesa"));

// base
cube([plate_w, plate_h, base_t]);

// cantos
translate([0, 0, base_t])
difference() {
    translate([ox - wall_th, oy - wall_th, 0])
        cube([pocket_w + 2*wall_th, pocket_h + 2*wall_th, wall_h]);
    // bolso do celular
    translate([ox, oy, -1]) cube([pocket_w, pocket_h, wall_h + 2]);
    // recortes no meio de cada lado (deixam só os cantos)
    translate([ox - wall_th - 1, oy + corner_l, -1])
        cube([wall_th + 1.5, pocket_h - 2*corner_l, wall_h + 2]);                 // esquerda
    translate([ox + pocket_w - 0.5, oy + corner_l, -1])
        cube([wall_th + 1.5, pocket_h - 2*corner_l, wall_h + 2]);                 // direita
    translate([ox + corner_l, oy - wall_th - 1, -1])
        cube([pocket_w - 2*corner_l, wall_th + 1.5, wall_h + 2]);                 // embaixo
    translate([ox + corner_l, oy + pocket_h - 0.5, -1])
        cube([pocket_w - 2*corner_l, wall_th + 1.5, wall_h + 2]);                 // em cima
}
