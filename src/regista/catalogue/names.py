"""Name pools for the catalogue's invented people: common given names and surnames per country and gender.

A person's name is a given name and a surname drawn at random from their nationality's pools, so the people are invented
(``regista.catalogue.define`` refuses a full name already used anywhere in the catalogue or the Regista League). The
pools are common names, as the league's are; any resemblance to a real player is a coincidence of common names.
"""

from __future__ import annotations


def _w(text: str) -> tuple[str, ...]:
    return tuple(text.split())


GIVEN_MEN: dict[str, tuple[str, ...]] = {
    "England": _w("Oliver Harry Jack George Charlie Jacob Alfie Thomas Joshua James William Ethan Mason Lewis Callum Kieran "
                  "Tyler Liam Ryan Connor Jamal Kai Reece Tyrese Nathan Jordan Owen Toby Elliot Ben Sam Joe Luke Aaron Leon "
                  "Rhys Max Archie Jayden Marcus"),
    "Scotland": _w("Fraser Euan Calum Lachlan Ross Finlay Murray Craig Gregor Angus Hamish Struan Kyle Blair Rory Scott"),
    "Ireland": _w("Cian Oisin Darragh Conor Sean Ciaran Eoin Fionn Padraig Shane Niall Ronan Cathal Tadhg Donal Eamon"),
    "Wales": _w("Dafydd Rhodri Gethin Iwan Owain Rhys Aled Gareth Huw Emyr Cai Osian Tomos Ioan Llyr Gruff"),
    "USA": _w("Tyler Brandon Austin Cody Dylan Logan Hunter Chase Mason Caleb Wyatt Garrett Trevor Blake Colton Brady "
              "Derek Evan Jaden Malik Andre Marcus Cole Grant Spencer Tanner Travis Reid Parker Bryce Isaiah Xavier"),
    "Canada": _w("Liam Noah Ethan Logan Owen Carter Brody Nolan Kieran Jonah Tristan Mathis Felix Gabriel Simon Desmond"),
    "Germany": _w("Lukas Leon Finn Jonas Elias Paul Felix Maximilian Niklas Tim Moritz Jannik Lennart Malte Jannis Florian "
                  "Tobias Sebastian Kevin Marcel Dennis Pascal Fabian Philipp Henrik Ole Timo Robin Kai Emre Can Deniz"),
    "Mexico": _w("Santiago Mateo Diego Emiliano Alejandro Leonardo Sebastian Rodrigo Ivan Jesus Eduardo Fernando Ricardo "
                 "Hector Arturo Omar Uriel Gael Brandon Axel Kevin Erick Alan Jair Edson Osvaldo Ulises Luis Raul Saul"),
    "Ghana": _w("Kwame Kwabena Kofi Yaw Kwaku Kojo Kwesi Nana Ebo Fiifi Kobina Selorm Elikem Mawuli Kelvin Prince "
                "Emmanuel Isaac Samuel Daniel Richard Eric Godfred Bernard Collins Ransford Jonathan Raphael"),
    "Spain": _w("Pablo Alejandro Daniel Hugo Alvaro Adrian Javier Sergio Mario Diego Raul Ivan Ruben Carlos Marcos Jorge "
                "Alberto Manuel Victor Iker Unai Asier Aitor Oscar Guillermo Rodrigo Nacho Andres Gonzalo Miguel Borja "
                "Samuel Hector Izan Eric Marc Pol Jaume Oriol"),
    "Japan": _w("Haruto Sota Yuto Riku Hinata Yuma Kaito Ren Sora Takumi Daiki Kenta Shota Ryota Kazuki Yusuke Tatsuya "
                "Naoki Hiroki Kohei Shun Keita Taiga Itsuki Sho Ryo Genki Koki Yuki Masato"),
    "Morocco": _w("Youssef Mohamed Amine Hamza Ayoub Anas Ilyas Mehdi Othmane Zakaria Soufiane Bilal Reda Karim Yassine "
                  "Adam Ismail Hicham Nabil Tarik Omar Achraf Walid Saad Badr Marouane Ayman Imad Hakim Khalid"),
    "Brazil": _w("Gabriel Lucas Matheus Guilherme Rafael Pedro Joao Gustavo Felipe Vinicius Thiago Caio Bruno Leonardo "
                 "Igor Diego Rodrigo Danilo Renan Wesley Everton Douglas Willian Kaique Davi Arthur Enzo Luan Yuri Murilo"),
    "Nigeria": _w("Chinedu Emeka Tunde Segun Ifeanyi Chukwuemeka Obinna Kelechi Babatunde Olumide Ayodele Femi Uche Nnamdi "
                  "Ikenna Chidi Adebayo Kehinde Taiwo Yusuf Ibrahim Sani Musa Victor Samuel David Godwin Peter Kingsley"),
}

GIVEN_WOMEN: dict[str, tuple[str, ...]] = {
    "England": _w("Olivia Amelia Isla Ava Mia Ivy Lily Isabella Rosie Sophia Grace Freya Poppy Evie Ella Ruby Daisy Chloe "
                  "Jessica Lauren Hannah Megan Bethany Abbie Katie Holly Millie Jade Leah Niamh Keira Tia Imani Zara Esme"),
    "Scotland": _w("Eilidh Kirsty Mhairi Isla Morven Ailsa Catriona Shona Fiona Rhona Iona Skye Morag Lorna"),
    "Wales": _w("Seren Cerys Ffion Nia Megan Lowri Carys Elin Angharad Bethan Mali Gwen Catrin Sian"),
    "Ireland": _w("Aoife Saoirse Ciara Niamh Siobhan Roisin Aisling Clodagh Orla Grainne Caoimhe Eimear Sinead Maeve"),
    "USA": _w("Madison Emily Hannah Ashley Taylor Kayla Morgan Alexis Sydney Brooke Kaitlyn Haley Abigail Avery Riley "
              "Peyton Mackenzie Kendall Jordan Savannah Camryn Delaney Jada Kennedy Reagan Sierra Paige Natalie Brianna"),
    "Canada": _w("Emma Chloe Sarah Megan Jessie Ashley Gabrielle Ariane Maude Laurence Kadeisha Shelina Vanessa Desiree"),
    "Mexico": _w("Ximena Valeria Camila Fernanda Daniela Mariana Andrea Alejandra Renata Regina Paola Karla Lizbeth Itzel"),
    "Japan": _w("Yui Hina Aoi Sakura Mio Rin Mei Riko Saki Nana Miyu Yuna Kana Haruka Moeka"),
    "Germany": _w("Lea Lena Laura Anna Leonie Hannah Sophie Johanna Lisa Svenja Merle Jule Pia Carla Klara Marie"),
}

SURNAMES: dict[str, tuple[str, ...]] = {
    "England": _w("Smith Jones Taylor Brown Wilson Evans Walker Wright Robinson Thompson White Hughes Edwards Green Hall Wood "
                  "Harris Lewis Martin Jackson Clarke Turner Hill Cooper Ward Morris King Baker Harrison Morgan Allen Mitchell "
                  "Kelly Barker Fletcher Shaw Holmes Bennett Chapman Marsh Pearce Lowe Webb Dixon Hunt Ellis Mason Booth"),
    "Scotland": _w("MacLeod Campbell Stewart Robertson Murray MacDonald Fraser Ross Henderson Paterson Ferguson Grant Hamilton "
                   "Sinclair Kerr Buchanan Munro Cameron"),
    "Ireland": _w("Murphy Byrne Ryan Brady Doyle Walsh McCarthy Gallagher Kennedy Lynch Quinn Brennan Nolan Fitzgerald "
                  "Moran Keane Dunne Hogan"),
    "Wales": _w("Jones Davies Williams Evans Thomas Roberts Hughes Lewis Morgan Griffiths Price Pritchard Powell Llewellyn "
                "Bevan Rees Howells Vaughan"),
    "USA": _w("Johnson Miller Davis Anderson Moore Martin Thompson Garcia Martinez Clark Rodriguez Lewis Lee Walker Young "
              "Allen Scott Adams Baker Nelson Carter Mitchell Roberts Turner Phillips Campbell Parker Collins Stewart Morris "
              "Murphy Cook Rogers Peterson Reed Bailey Bell Howard Ward Brooks Hayes Sullivan Russell Griffin Foster Bryant"),
    "Canada": _w("Tremblay Gagnon Roy Cote Bouchard Gauthier Morin Lavoie Fortin MacKenzie Fraser Campbell Leblanc Bergeron "
                 "Pelletier Ouellet"),
    "Germany": _w("Muller Schmidt Schneider Fischer Weber Meyer Wagner Becker Schulz Hoffmann Koch Richter Klein Wolf "
                  "Schroder Neumann Schwarz Zimmermann Braun Kruger Hofmann Hartmann Lange Werner Krause Lehmann Kohler "
                  "Maier Huber Kaiser Fuchs Peters Lang Scholz Jung Hahn Vogel Friedrich Keller Gunther Frank Berger"),
    "Mexico": _w("Hernandez Garcia Martinez Lopez Gonzalez Perez Rodriguez Sanchez Ramirez Cruz Flores Gomez Morales Vazquez "
                 "Reyes Jimenez Torres Diaz Gutierrez Ruiz Mendoza Aguilar Ortiz Moreno Castillo Romero Alvarez Mendez Chavez "
                 "Rivera Juarez Ramos Dominguez Herrera Medina Castro Vargas Guzman Velazquez Salazar"),
    "Ghana": _w("Mensah Owusu Asante Boateng Osei Agyeman Appiah Amoah Darko Adjei Ofori Acheampong Antwi Badu Frimpong "
                "Kyei Nkansah Opoku Sarpong Yeboah Gyamfi Ansah Amponsah Bonsu Danso Fosu Kusi Manu Oppong Tetteh Quaye"),
    "Spain": _w("Garcia Fernandez Gonzalez Rodriguez Lopez Martinez Sanchez Perez Gomez Martin Jimenez Ruiz Hernandez Diaz "
                "Moreno Alvarez Munoz Romero Alonso Gutierrez Navarro Torres Dominguez Vazquez Ramos Gil Ramirez Serrano "
                "Blanco Molina Morales Suarez Ortega Delgado Castro Ortiz Rubio Marin Sanz Iglesias Medina Garrido Cortes "
                "Castillo Santos Lozano Guerrero Cano Prieto Mendez Calvo Cruz Gallego Vidal Leon Marquez Herrera Pena"),
    "Japan": _w("Sato Suzuki Takahashi Tanaka Watanabe Ito Yamamoto Nakamura Kobayashi Kato Yoshida Yamada Sasaki Yamaguchi "
                "Matsumoto Inoue Kimura Hayashi Shimizu Yamazaki Mori Abe Ikeda Hashimoto Ishikawa Ogawa Okada Goto Hasegawa "
                "Murakami Kondo Ishii Sakamoto Endo Aoki Fujii Nishimura Fukuda Ota Miura"),
    "Morocco": _w("Alaoui Bennani Idrissi Tazi Berrada Benali Chraibi Fassi Amrani Ouazzani Lahlou Kettani Bouzid Sabri "
                  "Mansouri Haddad Belkadi Rami Ziani Naciri Tahiri Zerouali Benjelloun Saidi Moussaoui Hajji Bakkali Rahmouni "
                  "Kabbaj Laaroussi Ouali Charki Daoudi Lamrani Filali"),
    "Brazil": _w("Silva Santos Oliveira Souza Rodrigues Ferreira Alves Pereira Lima Gomes Costa Ribeiro Martins Carvalho "
                 "Almeida Lopes Soares Fernandes Vieira Barbosa Rocha Dias Nascimento Andrade Moreira Nunes Marques Machado "
                 "Mendes Freitas Cardoso Ramos Goncalves Santana Teixeira Araujo Pinto Moraes Correia Campos"),
    "Nigeria": _w("Okafor Adeyemi Okonkwo Balogun Eze Nwosu Adebayo Ogunleye Chukwu Olawale Ibekwe Afolabi Nnadi Okoro "
                  "Bello Ogundipe Oyelaran Akinola Uzor Obi Onyeka Adeleke Ajayi Lawal Oladipo Bakare Ogbonna Nwachukwu "
                  "Ojo Salami Fashola Danjuma Akande"),
}


def pools(nationality: str, gender: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(given names, surnames) for a nationality and gender."""
    given = (GIVEN_WOMEN if gender == "women" else GIVEN_MEN)[nationality]
    return given, SURNAMES[nationality]
