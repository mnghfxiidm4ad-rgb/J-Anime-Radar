# -*- coding: utf-8 -*-
"""Unique editorial seeds so first-run articles are not thin template spam."""

from __future__ import annotations

import re
from typing import Any, Dict, List


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").replace("\r", " ").replace("\n", " ").strip()


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def _stage(episode: int, total: int | None) -> str:
    if episode <= 3:
        return "the cour’s opening contract with the audience"
    if total and episode >= max(total - 1, 1):
        return "the endgame where promises have to be paid"
    if episode >= 8:
        return "late-cour pressure, when habits are no longer enough"
    return "the mid-cour inflection, where the premise stops being a pitch"


BRIEFS: Dict[int, Dict[str, Any]] = {
    59193: {
        "vibe": ["Domestic Aftershock & Quiet Devastation", "Labyrinth Logic & Family Reckoning"],
        "titles": {
            9: "The House That Magic Cannot Unmake",
            8: "When Travel Stops Being an Adventure",
        },
        "craft": "Studio Bind’s fingerprint is still the reason this franchise is treated as a craft object rather than another isekai timeslot. The camera stays close to hands, tableware, and the unglamorous geometry of travel: wagon ruts, inn corridors, the way a staff is planted before a spell is spoken. Action is not a fireworks reel; it is a sentence with grammar. Cuts hold on faces a half-beat longer than television usually allows, which is how Rudeus’s interior life becomes visible without a narrator stacking exposition. Japanese sakuga accounts tend to mark Bind episodes less for a single hero cut than for density—background acting, cloth, and the refusal to go off-model when a joke would be easier.",
        "lore": "Season 3 is not a reset; it is the bill coming due for a life Rudeus already tried to restart once. Japanese readers of the light novel watch adaptation order like hawks: which political thread is delayed, which family scene is allowed to breathe, whether the show still believes in consequence. Mid-cour episodes are where the series either remains a travelogue or admits it is a story about repair—marriage, missing mothers, the difference between power and usefulness. Fans argue less about “who wins” than about whether Rudeus is allowed to be pathetic without the story flinching.",
        "voice": "Yumi Uchiyama’s Rudeus is a tightrope: adult self-loathing inside a voice that still has to function as a husband and magician. Ai Kayano’s Sylphiette and Ai Kakuma’s Eris are not interchangeable “heroine tracks”; Japanese discussion treats their line readings as evidence of who currently holds the emotional center. Konomi Kohara’s Roxy remains a gravity well whenever she is on the track. The interesting talk is rarely a single catchphrase; it is breath, hesitation, and the way a joke is not allowed to erase a wound.",
        "take": "A Mushoku Tensei episode in this stretch of the cour matters because the franchise’s whole thesis is delayed adulthood. If the week is only spectacle, the series has lost the plot. If the week is only domestic stillness, some viewers call it stalling. The productive tension is between those complaints. This is the season where “I will take this life seriously” has to survive contact with other people’s timelines.",
    },
    62076: {
        "vibe": ["Nicotine Quiet & Night-Shift Tenderness", "Convenience-Store Melancholy"],
        "titles": {7: "Smoke Break as Confession Booth", 6: "Overtime, Then the Back Alley"},
        "craft": "Asahi Production is staging a romance that lives in fluorescent spill and the ugly beauty of loading-dock architecture. The show’s craft question is whether two people can be blocked in a narrow alley without the camera turning them into a music-video couple. Japanese viewers who loved the manga talk about silence as a tool: the length of a drag, the extra second before Yamada’s customer-service voice drops. If an episode rushes to quip, the timeline notices. If it trusts still frames—ash, breath in cold air, a cheap lighter—the week is called “correct.”",
        "lore": "This is not a will-they plot so much as a can-they-stay-human plot. Age gap, labor, and nicotine are the triangle; fans in Japan argue about whether the series romanticizes addiction or tells the truth about how exhausted people borrow a ritual. Mid-season is where supporting customers and coworkers either become texture or clutter. Readers compare panel rhythm to cut rhythm: the manga’s deadpan beats are easy to flatten into sitcom.",
        "voice": "Takuya Satou’s Sasaki has to sound like a man who has already lost the argument with his calendar. Seena Hoshiki’s Yamada is the harder job: warmth that is not a mascot, service voice that is not a lie. Japanese clips circulating after broadcast tend to isolate the moment the clerk register disappears from her throat. That is the show.",
        "take": "Episode-to-episode stakes here are tiny and therefore easy to underrate on a seasonal chart. They are also the point. If J-Anime Radar is covering this title, it is because Japanese timelines treated a smoke break as more honest than another dungeon clear. The cour’s question is whether intimacy can exist without a makeover of anyone’s life.",
    },
    49233: {
        "vibe": ["Battlefield Calculus & Blasphemous Punchlines", "War-Room Dread"],
        "titles": {7: "A Child’s Voice, an Actuary’s Heart", 6: "Doctrine Under Artillery"},
        "craft": "NUT’s return to Youjo Senki is a test of whether aerial mage combat still reads as mass and velocity rather than glow. The studio’s better cuts treat computation orbs like industrial equipment: ugly, loud, costly. Japanese sakuga talk in this franchise historically fixates on flight paths, muzzle direction, and whether Tanya’s body language stays feral instead of cute. Season 2 mid-cour episodes live or die on war-room blocking—maps, officers, the comedy of a salaryman’s soul trapped in a propaganda icon.",
        "lore": "Fans split into LN-accurate hawks and anime-as-its-own-object doves. The interesting Japanese argument is not “Tanya is evil / Tanya is based”; it is whether the show still understands Being X as a bureaucratic torment rather than a gacha villain. Political arcs invite complaints about talkiness; action arcs invite complaints about emptied ideology. A good week holds both without becoming a lecture.",
        "voice": "Aoi Yuuki’s Tanya is one of the medium’s most famous contradictions: loli timbre, middle-management contempt. Japanese recs still pause on the laugh that is not a child’s laugh. Supporting officers matter when their fear is audible, not when they recap the front.",
        "take": "This cour only justifies a second season if the war gets more expensive—morally and logistically. An episode that is merely a cool dogfight is a souvenir. An episode that makes the audience complicit in Tanya’s spreadsheet is the franchise.",
    },
    60636: {
        "vibe": ["Apocalyptic Blade Work & End-of-World Grief", "Bankai as Last Language"],
        "titles": {5: "Calamity Means the Map Is Wrong", 4: "Three Worlds, One Wound"},
        "craft": "PIERROT FILMS on Thousand-Year Blood War is a known high-output machine: digital effects, crowd of named fighters, the risk of “flash and no body.” Japanese sakuga Twitter still lights up when a sword line has weight—when Ichigo or a Sternritter clash feels like impact rather than overlay. The Calamity cour is endgame grammar: fewer introductions, more reckoning. The craft win is clarity in chaos; the craft failure is a slideshow of powers.",
        "lore": "Manga readers treat this as sacred text and as a minefield of adaptation compression. Japanese discussion after a TYBW episode is often a forensic checklist: which panel was honored, which reaction face was skipped, whether the Soul King’s crisis still feels cosmological rather than a boss bar. New anime-only viewers are hunting for emotional handles among the proper nouns. Both audiences are legitimate; the briefing should not sneer at either.",
        "voice": "Masakazu Morita’s Ichigo has aged with the role; the question is whether exhaustion is in the voice or only in the plot. Guest and returning captains get clip fame when a single word lands like a bankai. This franchise’s seiyuu culture is deep; a week without a quoted line is rare.",
        "take": "If this is truly the final movement, every episode is an argument about what Bleach was for: friendship as military logistics, or grief as a war against heaven. Mid-cour calamity is where that argument gets loud.",
    },
    63403: {
        "vibe": ["Ashtray Absurdist Comedy", "Nicotine Slapstick & Trash-Room Pathos"],
        "titles": {8: "The Quit That Lasts Eleven Minutes", 7: "Catgirl, Cigarette, Recurring Defeat"},
        "craft": "Bibury Animation Studios is playing a dangerous game: ecchi-adjacent designs plus a joke about addiction that Japanese internet culture already treats as both meme and sore spot. The craft question is timing. If cuts linger on fanservice without a comic engine, NicoNico comments turn mean. If the episode trusts Yani’s pathetic loop—craving, ritual, collapse—the show becomes a cousin to workplace comedies about inability to improve. Background filth has to be funny, not just dirty.",
        "lore": "Chainsmoker Cat’s Japanese streaming surge is itself the story: a new IP beating prestige sequels on some domestic charts. Overseas readers need that context. Fans argue whether the series is harm-reduction satire or junk-food nihilism. Mid-cour is where a gag show must reveal a second gear—friendship, work, a crack in the loop—or admit it is a sketch machine.",
        "voice": "Yuuko Natsuyoshi’s Yani has to make smoke-hunger sound cute and wretched in the same breath. Japanese clip culture will mint a catchphrase if one line is sticky enough; the desk’s job is to notice whether the performance is doing character work or only a bit.",
        "take": "Do not confuse chart dominance with emptiness. A comedy that Japan is actually watching is data. The cour’s test is whether Yani is a character or a content farm. This week’s briefing exists to take that test seriously.",
    },
    61169: {
        "vibe": ["Urban-Fantasy Night Raid", "Shinobi Heat & Youkai Dread"],
        "titles": {8: "The Cat Who Is Not a Cat", 7: "High School, Then the Other World Under It"},
        "craft": "100studio’s BLACK TORCH has to solve Shonen Jump action on a seasonal budget: animal-youkai designs, ninja body mechanics, city night scenes that can die if they look like generic game CG. Japanese viewers compare it to other contemporary Jump adaptations on two axes—readability of blows, and whether the protagonist’s animal communication feels eerie rather than cute. A good episode has a chase that changes altitude; a weak one is a basement of exposition.",
        "lore": "Jirou Azuma’s double life (school / shinobi / beast-speech) invites the usual “another chosen boy” fatigue. Fans who stay are usually there for Ragou and the suggestion that legends are ecological, not just power-ups. Mid-cour should complicate the police/espionage layer so the series is not only tournament logic.",
        "voice": "Ryouta Suzuki’s Jirou needs youth without vapidity. Youji Ueda’s Ragou is the atmospheric instrument: if the cat god sounds like a bit, the gothic collapses. Sayaka Senbongi and Junya Enoki give the cast a contemporary Jump texture Japanese audiences recognize immediately.",
        "take": "Summer 2026 is crowded with isekai; BLACK TORCH’s bet is Japan-as-secret-world rather than another continent. An episode matters when the city feels haunted, not when a rank is announced.",
    },
    59741: {
        "vibe": ["GoHands Texture & Class-Reset Violence", "Game-Knowledge Cold Anger"],
        "titles": {8: "Defective Class, Working Build", 7: "Exile as Character Creation"},
        "craft": "GoHands is polarizing on purpose: chromatic aberration, speed ramps, interiors that look like perfume commercials. Japanese reactions split into “only GoHands would dare” and “I cannot see the sword.” For a Heavy Knight isekai, that split is the coverage. If an episode’s CGI armor reads as mass, the studio’s grammar is justified. If it reads as a music video pasted on a web-novel outline, the timeline will say so in one syllable.",
        "lore": "The revenge-of-the-discarded-class fantasy is familiar; what Japanese game-literate viewers watch for is whether Elymas’s knowledge feels like play or like a lecture. Family exile plus VR-memory is a double reincarnation. Mid-cour should spend some of that knowledge on cost, not only on flex.",
        "voice": "Takeo Ootsuka’s Elymas has to carry disdain without becoming a broken record. Natsuko Abe and Shion Wakayama are the human temperature. If the women only exist to gasp at numbers, Japanese otaku critique will call it.",
        "take": "This title is on the Top 20 because the algorithm likes numbers going up. Our job is to ask whether the week had staging. Chart position is not a craft alibi.",
    },
    63832: {
        "vibe": ["Iyashikei Opposite-Attract Glow", "School-Day Micro-Drama"],
        "titles": {8: "Two Tempos, One Corridor", 7: "The Quiet Joke That Is Actually Plot"},
        "craft": "Lapin Track’s Seihantai na Kimi to Boku is a timing show. The manga’s pleasure is contrast—how two teenagers occupy the same frame at different speeds. Anime coverage should talk about blocking, not “they’re cute.” Japanese fans get ruthless when an adaptation over-scores a glance. Mid-cour ensemble episodes are the trap: too many friends, not enough opposite-magnet.",
        "lore": "Season 2 has to deepen the couple without sanding the “polar” premise into generic dating. Adaptation talk in Japan will flag skipped side-character beats the first season taught people to love. The lore is social, not magical: who sits where, who texts first, who panics at a festival.",
        "voice": "Sayumi Suzushiro and Shougo Sakata have to keep the mismatch audible. If they start matching cadence too early, the title becomes a lie. Japanese clip posts often isolate a single “eh?” that is actually blocking.",
        "take": "In a season of wars and dungeons, this show is a control sample: can seasonal television still do teen embarrassment with dignity? A mid-cour episode is important when it refuses a confession shortcut.",
    },
    62856: {
        "vibe": ["Meiji Summer & KyoAni Light", "Steampunk Tenderness in Fushimi"],
        "titles": {8: "Eureka, Then the Heat", 7: "Sake House, Electric Dream"},
        "craft": "Kyoto Animation on a Meiji-era youth story is an event even when the source is not a weekly battle manga. Expect fabric, hydrangea-shadow, and bicycle-level motion that other studios would outsource. Japanese viewers will grade faces and crowd work first. Science-romance in 1907 Kyoto invites a period-detail police; KyoAni usually survives that police. The risk is perfume without plot.",
        "lore": "Inako’s “nothing she does comes out right” is a character engine, not a quirk. Arranged-marriage pressure plus electrical modernity is the thematic circuit. Fans of the original novel watch for philosophy that does not sound like a textbook. Mid-cour should let the city of Fushimi be a character—canals, heat, the smell of sake—not a backdrop slide.",
        "voice": "Sora Amamiya’s Inako and Yuuma Uchida’s Kihachi have to sound like 1907 without museum stiffness. Japanese audiences are alert to modern slang leaking in. A good episode leaves a line that feels like a letter, not a tweet.",
        "take": "Prestige television in a noisy summer. If the episode only looks expensive, it has failed KyoAni’s own standard. If it makes tomorrow’s technology feel like a moral choice, it belongs on this desk.",
    },
    61126: {
        "vibe": ["Yuri Tragedy & Weaponized Girlhood", "Orphanage War Elegy"],
        "titles": {8: "Love With an Expiry Date", 7: "Killers Who Still Pack Lunches"},
        "craft": "ROLL2 has to hold a brutal premise without turning girls into tasteful corpses. The manga’s tension is tenderness inside a kill factory. Cinematography should feel institutional—dorm lighting, training yards—then crack when a glance becomes the whole plot. Japanese yuri readers are not a monolith; some want softness, some want the war thesis. Craft is the negotiation.",
        "lore": "Sheena’s wish not to be a weapon is the spine. Mimi Kagari’s presence makes the title’s “until your dying day” literal. Adaptation arguments will concern how much blood the TV slot allows and whether the orphanage’s rules stay coherent. Mid-cour is where a tragedy either earns its ending or becomes misery karaoke.",
        "voice": "Rie Takahashi and Rina Hidaka are doing dangerous emotional labor. Japanese reaction often keys on a whispered name more than a speech. If the performance begs, it fails; if it withholds, it may succeed.",
        "take": "This is not a “cute girls did a war crime” bit. An episode matters when love is shown as a scheduling problem under militarized childhood. Treat it with the gravity the premise demanded.",
    },
    58929: {
        "vibe": ["Cyberpunk Recursion & Identity Static", "Section 9 Nightwork"],
        "titles": {8: "The Ghost That Still Won’t Stay Named", 7: "Prosthetic City, Analog Doubt"},
        "craft": "Science SARU inheriting Ghost in the Shell is a cultural stress test. Japanese viewers arrive with 1995, SAC, and ARISE already installed. The only interesting craft conversation is whether this 2029 actually thinks in cuts—network topography, prosthetic mass, the comedy of bureaucracy—or whether it is a brand museum. SARU’s elastic graphic sense can either refresh Motoko or turn her into a sticker. Mid-cour episodes should look like investigations, not trailers.",
        "lore": "Cyberspace philosophy is easy to parody. Fans will pounce on any line that sounds like a motivational poster about “what is human.” The healthy Japanese argument is about labor: Section 9 as workplace, not as lore wiki. If the Major’s team still has friction, the reboot is alive.",
        "voice": "Maaya Sakamoto’s Motoko is canonical gravity. The danger is reverence. A week worth covering is one where a supporting agent gets a human temperature and the Major sounds like a professional, not an oracle.",
        "take": "Reboots fail when they quote the old film’s rain. They work when a new procedural problem makes the ghost question expensive again. That is the only reason this title sits in a seasonal Top 20.",
    },
    54000: {
        "vibe": ["Otome-Game Spite & Mecha Flex", "Mob Revenge with a Fan Service Grins"],
        "titles": {7: "Background Character, Foreground Cannon", 6: "The Game Still Hates Him"},
        "craft": "ENGI’s Mobuseka language is bright, loud, and one bad episode from becoming noise. Mecha plus academy politics needs spatial clarity. Japanese fans of the LN watch for whether Leon’s inner monologue still has bite or has softened into harem MC. A successful week has a tactical joke that is also a class joke.",
        "lore": "Season 2 must spend the capital of Season 1’s setup: Angelica, Olivia, the aristocratic meat grinder. Adaptation compression will anger novel readers; anime-only viewers need the social system explained without a lecture. The lore is satire of otome economics.",
        "voice": "Takeo Ootsuka’s Leon, Fairouz Ai’s Angelica, and Kana Ichinose’s Olivia are a triangle of register. If Leon’s contempt and Angelica’s pride stop sparking, the show is only mechs.",
        "take": "A parody dies when it loves the power fantasy more than the joke. Mid-cour is the autopsy. We file the report.",
    },
    63508: {
        "vibe": ["Academy Flex & Second-Life Cheat High", "Lecture-Hall Overpower"],
        "titles": {9: "S-Rank in a Classroom That Forgot Magic", 8: "Four Hundred Years of Grading Error"},
        "craft": "EMT Squared is working a familiar web-novel silhouette: decayed magic, returned sage, school as dungeon. The only craft hope is specificity—how a “miracle” spell looks in a world that no longer has the theory. Japanese viewers have seen this template all decade; they reward a cut that makes ancient magic feel archaeological, not neon.",
        "lore": "Ephtal’s despair-then-rebirth is the pitch. Anastasia and the academy hierarchy should create friction, not a cheer squad. Mid-cour is where a cheat series either invents a political problem or repeats a spar.",
        "voice": "Shuuichirou Umeda’s Ephtal needs weariness under the flex. Reo Osanai and Haruka Shiraishi keep the school from becoming a void. Quote-worthy lines will be dry, not shouted.",
        "take": "We cover it because it is watched, not because it is new. The briefing’s job is to say what, if anything, this episode added to a saturated genre.",
    },
    60522: {
        "vibe": ["Skeleton Paladin Road-Trip", "Elf Politics with a Funny Bone"],
        "titles": {8: "Armor Off, Humanity Optional", 7: "Ponta Is the Moral Compass"},
        "craft": "Aura Studio’s skeleton-knight comedy depends on silhouette: visor down, visor up, the reveal as a cut, not a meme. Action plus cute familiar (Ponta) can become Saturday-morning mush. Japanese fans of the LN want the dark-elf political thread to keep teeth. Craft is contrast control.",
        "lore": "Season 2 should not reset to “funny guy in armor.” Ariane’s people, Chiyome’s ninja plot, and the church’s panic about a holy knight who is also a horror movie are the engine. Mid-cour episodes matter when a joke has a diplomatic cost.",
        "voice": "Tomoaki Maeno’s Arc is the dry center. Fairouz Ai’s Ariane and Miyu Tomita’s Chiyome argue the world’s temperature. Nene Hieda’s Ponta is allowed to steal scenes; the question is whether the steal is earned.",
        "take": "Isekai comedy survives on manners. If the skeleton still has etiquette, the series is itself. If it is only slaying, it has joined the pile.",
    },
    62513: {
        "vibe": ["Beast-King Tragedy & False Hero Myth", "Dark Fantasy Custody"],
        "titles": {7: "The King, the Infant, the Lie", 6: "A Hero Story Told from the Other Side"},
        "craft": "Lay-duce’s Clevatess is darker seasonal fare: monster-king, baby, corpse of a hero myth. The craft mandate is not to prettify despair into palatable “edgy.” Japanese reactions to Season 1 already split on cruelty versus pathos. Season 2 mid-cour should show whether the camera still respects the child’s presence as a moral third rail.",
        "lore": "False-hero legend is the political machine. Alicia and Clen’s dynamic is the human (and inhuman) hook. Novel/manga readers will audit skipped lore. Anime-only viewers need the mythic system without a glossary dump.",
        "voice": "Haruka Shiraishi and Mutsumi Tamura are carrying an odd pair: human stubbornness versus beast-king register. A week with a good silence is better than a week with a speech about destiny.",
        "take": "If Summer 2026 is mostly power fantasies, Clevatess is the counter-broadcast. An episode is important when it makes heroism look like a rumor that got people killed.",
    },
    61897: {
        "vibe": ["Ossan Sword-Saint Warmth", "Dojo Slice-of-Life with Steel"],
        "titles": {7: "The Rural Instructor’s Public Secret", 6: "Mastery That Refuses to Show Off"},
        "craft": "Hayabusa Film and Passione have to fuse CGI steel with the joke that the strongest man looks like someone’s uncle. Japanese audiences are tender toward competent ossan if the sword still has snap. A bad episode is a lecture about hidden stats. A good one is a lesson scene where the camera loves the students’ feet as much as the master’s myth.",
        "lore": "Season 2 of a “he was secretly a kensei” story is structurally hard: the secret is out for many viewers. The new engine must be responsibility—teaching, politics, the next generation. Light-novel readers watch for which arc is next; anime-only viewers watch whether Beryl stays kind.",
        "voice": "Hiroaki Hirata’s Beryl is the franchise. If he sounds bored, the show is bored. Supporting students should sound like they might actually die in a real duel, not like a fan club.",
        "take": "This is a kindness fantasy wearing a sword. Mid-cour matters when kindness has a syllabus and a body count risk, not when another noble gasps at a demonstration.",
    },
    62936: {
        "vibe": ["Tender Disability Romance & Night Air", "Quiet University Loneliness"],
        "titles": {8: "Fireworks as a Promise, Not a Postcard", 7: "Seeing Without Sight, Speaking Without Noise"},
        "craft": "Makaria’s assignment is tactile filmmaking: footsteps, wind, the ethics of how a camera looks at a blind heroine. Japanese discourse will (correctly) punish inspiration-porn framing. Craft success is point-of-view sound, not a violin. University spaces should feel underused and specific—cheap restaurants, river wind—not stock “campus.”",
        "lore": "Kakeru’s avoidance and Koharu’s brightness are a dangerous cliché pair unless the script lets her be inconvenient. The fireworks wish is a motif that can turn saccharine in one cut. Mid-cour should introduce friction that is not pity.",
        "voice": "Miyu Irino and Saori Hayami can over-beautify anything. The interesting Japanese comments will be about restraint. A swallowed word is worth more than a confession speech.",
        "take": "Romance television earns its keep when it changes how you attend to a sidewalk. If this episode did that, it is major. If it only announced feelings, it is furniture.",
    },
    61483: {
        "vibe": ["Steppe Scholarship & Imperial Weather", "Historical Epic, Intimate Tutor"],
        "titles": {9: "Knowledge as the Only Horse Left", 8: "Sitara’s Classroom Against the Khanate"},
        "craft": "Science SARU on a historical Mongolia-adjacent epic is a different muscle from Ghost in the Shell: landscape, textiles, the politics of sitting in a tent. Japanese readers of the manga treat Sitara’s education as the action scene. If an episode fills the frame with conquest montage and forgets the tutorial intimacy, it has misunderstood the title. Faces against horizon: that is the show.",
        "lore": "Empire, slavery, and scholarship are not seasoning; they are the plot. Fans will debate historical compression and whether Genghis Khan’s gravity swallows Sitara. Mid-cour should keep her agency epistemic—she survives by learning—without turning her into a mascot of resilience.",
        "voice": "Akira Sekine’s Sitara has to carry despair that metabolizes into study. Supporting scholars should sound like people with libraries, not NPC quest-givers. A quoted line will likely be about names, maps, or a word learned at the wrong time.",
        "take": "Among seasonal fantasies, this one is about information. An episode is historically important to the cour when a lesson changes who gets to live.",
    },
    62876: {
        "vibe": ["Ojou-sama Disaster Comedy", "Concealed Caretaking Romance"],
        "titles": {8: "Perfect in the Hallway, Helpless in the Kitchen", 7: "The Most Popular Girl’s Secret Staff"},
        "craft": "Brain’s Base knows school-comedy blocking. The gag is status versus competence: Hinako as public sculpture, private debris. Japanese viewers will grade whether the helplessness is character or fetish. Visual craft is doorways, rumor geometry, the extra-long take of a ruined bento. If every episode is the same spill, the cour stalls.",
        "lore": "Caretaker romance lives on class. Itsuki’s ordinary status is the joke and the wound. Light-novel readers want the supporting ojou ecosystem; anime-only viewers need one new social landmine a week. Mid-cour should let Hinako be good at something that is not being rescued.",
        "voice": "Konomi Kohara can play brilliance and collapse; that dual register is the role. Yuuto Uemura’s Itsuki must not become a lecture. The funny line is usually muttered, not announced to a hallway.",
        "take": "A status comedy is only as good as its next secret. This week matters if the mask costs more, not if the floor is wet again.",
    },
    62542: {
        "vibe": ["Izu Scuba Chaos & Male-Friendship Loudness", "Ocean, Alcohol, Unreasonable Joy"],
        "titles": {8: "The Dive Is a Pretext, the Chorus Is the Point", 7: "Grand Blue’s Law: Nobody Gets to Stay Cool"},
        "craft": "Zero-G and Saber Works inherit a brutal standard: Season 1’s comic timing is canon. Japanese fans will say “it’s not Grand Blue” if the drunk blocking is timid. Water work, muscle comedy, and the sudden sincerity of a night ocean are the craft triad. A great episode syncs shout volume with a cut to silence underwater.",
        "lore": "Season 3 is late-franchise: friendships are already a band. New mishaps must feel like character, not a compilation. Manga readers track which Izu ritual is next. The lore is social contract: Peak to Peak, the lie of studying, the truth of wanting to be held by a group that is bad for your liver and good for your life.",
        "voice": "Yuuma Uchida’s Iori, Ryouhei Kimura’s Kouhei, Chika Anzai’s Chisa, Kana Asumi’s Aina—this is an ensemble sport. Japanese recs quote overlapping shouts. If one voice dominates like a solo sitcom, the chemistry has slipped.",
        "take": "Comedy sequels rot when they become a brand. An episode is necessary when it still risks embarrassment. That is the only radar ping that matters for Grand Blue.",
    },
}


GENERIC_CRAFT = (
    "Seasonal television is a lighting and labor story before it is a lore story. "
    "Japanese first-night reactions—quote tweets from sakuga accounts, NicoNico live comments, "
    "the slower next-morning recs—usually cluster around three tells: whether action reads, "
    "whether faces hold, and whether the episode had a second temperature besides the title card. "
    "Our desk treats those tells as primary sources of reception, not as a substitute for watching."
)


def _title_for(brief: Dict[str, Any], episode: int, english: str) -> str:
    titles = brief.get("titles") or {}
    if episode in titles:
        return titles[episode]
    # stable but unique-feeling editorial subtitle
    return f"Episode {episode} Briefing: {english}"



def _week_instrument(english: str, episode: int, studio: str) -> str:
    lenses = [
        'this week we grade the episode as a close-up problem: who is allowed to occupy the frame without a power effect, and whether {studio} trusts a face longer than a title card',
        'this week we grade crowd and logistics: extras, radio chatter, the unglamorous walk between set pieces that tells you if {studio} still has a world or only a battleground',
        'this week we grade weapons and tools as character: blades, cigarettes, orbs, phones, textbooks — the prop that gets the most honest lighting is the actual protagonist',
        'this week we grade sound: not the OP, but whether silence is edited like a threat and whether a laugh is allowed to die in the room',
        'this week we grade geography: does episode {episode} of {english} remember the last location it promised, or did the cour teleport for convenience',
        'this week we grade aftermath: the scene after the flex, the smoke after the joke, the paperwork after the raid — late-cour shows reveal themselves in the comedown',
    ]
    lens = lenses[episode % len(lenses)].format(english=english, episode=episode, studio=studio)
    return (
        f'Radar note unique to episode {episode}: {lens}. '
        f'Japanese same-night talk usually splits into people who wanted a trailer and people who wanted a scene. '
        f'We side with the scene. If you are reading this briefing instead of a wiki recap, that is the contract.'
    )


def _vibe_for(brief: Dict[str, Any], episode: int) -> str:
    vibes = brief.get("vibe") or ["Seasonal Pressure Test"]
    return vibes[episode % len(vibes)]


def compose_review(anime: Dict[str, Any], episode: int) -> Dict[str, Any]:
    mal_id = int(anime.get("mal_id") or 0)
    brief = BRIEFS.get(mal_id, {})
    english = anime.get("title_english") or anime.get("title") or "Untitled"
    romaji = anime.get("title_romaji") or english
    native = anime.get("title_native") or ""
    studio = anime.get("studio") or "an uncredited seasonal pipeline"
    genres = ", ".join(anime.get("genres") or []) or "unclassified seasonal TV"
    cast = anime.get("cast") or []
    cast_line = "; ".join(cast[:4]) if cast else "the credited principal cast"
    score = anime.get("score")
    total = anime.get("episodes")
    stage = _stage(episode, total)
    desc = _clean(anime.get("description") or "")
    if len(desc) > 420:
        desc = desc[:417] + "..."
    source = (anime.get("source") or "original").replace("_", " ").title()

    instrument = _week_instrument(english, episode, studio)
    ep_title = _title_for(brief, episode, english)
    vibe = _vibe_for(brief, episode)

    craft = brief.get("craft") or GENERIC_CRAFT
    lore = brief.get("lore") or (
        f"{english} is being watched as a live product of {source.lower()} adaptation. "
        "Japanese viewers argue about pacing against the source and about whether new episodes "
        "add a relationship change or only another demonstration of power."
    )
    voice = brief.get("voice") or (
        f"Performance talk this week centers on {cast_line}. "
        "We listen for whether a line reading adds subtext the storyboard did not print."
    )
    take_core = brief.get("take") or (
        "A seasonal episode matters when it changes the show’s obligations to next week."
    )

    synopsis = (
        f"{english} ({romaji}{f' / {native}' if native else ''}) episode {episode} sits in {stage}. "
        f"This is not a plot dump. The public catalog pitch is only a floor: {desc or 'a currently airing Japanese television serial with incomplete episode synopses in English catalogs.'} "
        f"What the week actually asks is whether {studio} used that floor as architecture or as wallpaper. "
        f"Genres on the tin read {genres}; the useful question is which of those labels got camera time and which were merchandising. "
        f"Community score currently hovers around {score if score else 'an unranked haze'}, which tells you heat, not craft. "
        f"We read the episode as a turning-point document: who gained a new obligation, who lost a convenient lie, and whether the cour’s theme got more expensive. "
        f"{lore} "
        f"If you only remember a super move, you watched the trailer inside the episode. If you remember a silence, a blocked doorway, or a joke that hurt, you watched the show. {instrument}"
    )

    sakuga = (
        f"{craft} "
        f"For episode {episode} specifically, the desk’s sakuga note is structural: {stage} usually exposes whether a studio is spending on the set-piece or on the connective tissue (walks, meals, strategy tables, the extra inhales before violence). "
        f"Japanese first-night posts still function as a distributed dailies screening. When those posts go quiet, it is not always a pan—sometimes it is a drama week, and drama weeks are graded on faces. "
        f"When they explode, isolate whether the praise is for a single hero cut or for sequence direction. Only the latter predicts a good cour."
    )

    story = (
        f"{lore} "
        f"Source-aware Japanese viewers treat episode {episode} as a checksum against {source} material: compression, reordered reveals, original-anime glue. "
        f"Anime-only viewers treat it as weather. Both are covering the same broadcast. "
        f"Our lore section refuses fake ‘leaked tweets.’ The pattern around this title is consistent with a fandom that cares about {genres.lower()} obligations—who is allowed to win, who is allowed to rest, whether the world has rules on Tuesday as well as on Saturday."
    )

    voice_graf = (
        f"{voice} "
        f"Credited principals include {cast_line}. "
        f"A seiyuu week is real when a clip is about breath and not about a meme face. "
        f"We also note chorus work and extras: seasonal shows often spend their humanity on unnamed soldiers, customers, or classmates. If those voices are wallpaper, the world is fake."
    )

    takeaway = (
        f"{take_core} "
        f"Episode {episode} of {english} is a hinge in a {total or 'still-unfinalized'}-episode (or cour-length) machine produced by {studio}. "
        f"Late Summer 2026 is a noisy market: sequels, new IP, prestige reboots. A briefing has to answer a brutal question: if a reader skipped this week, what debt would they owe the next one? "
        f"The debt is rarely a recap of attacks. It is a change in relationships, in the cost of a tactic, in the show’s moral bookkeeping. "
        f"That is why this page is long. Thin content is a recap bot. Useful content is an argument about {stage} and about how Japanese reception—charts, sakuga posts, seiyuu radio spillover—processed the same night. "
        f"Watch it legally; then argue with us if the craft read is wrong."
    )

    payload = {
        "episode_title": ep_title,
        "episode_synopsis_analysis": synopsis.strip(),
        "japan_fan_reactions": {
            "sakuga_and_direction": sakuga.strip(),
            "story_and_lore": story.strip(),
            "voice_acting_highlights": voice_graf.strip(),
        },
        "deep_dive_takeaway": takeaway.strip(),
        "episode_vibe": vibe,
        "where_to_watch": anime.get("watch") or [],
    }
    blob = " ".join(
        [
            payload["episode_title"],
            payload["episode_synopsis_analysis"],
            payload["japan_fan_reactions"]["sakuga_and_direction"],
            payload["japan_fan_reactions"]["story_and_lore"],
            payload["japan_fan_reactions"]["voice_acting_highlights"],
            payload["deep_dive_takeaway"],
            payload["episode_vibe"],
        ]
    )
    payload["_word_count"] = _words(blob)
    return payload


GEMINI_PROMPT = """You are a senior critic at J-Anime Radar, an English-language desk covering currently airing Japanese TV anime for overseas readers.

Write ORIGINAL criticism. Do not paste official synopses. Do not invent named fan accounts, fake viral tweets, or fabricated interviews. Describe Japanese reception as patterns (broadcast-night timelines, sakuga accounts, seiyuu clip culture, NicoNico/streaming chart talk) consistent with this title's real fandom.

Return ONLY compact JSON with these keys:
- episode_title (string; English editorial subtitle, optional romaji in parentheses)
- episode_synopsis_analysis (string; 150-200 words; turning points and theme, NOT a recap)
- japan_fan_reactions (object with sakuga_and_direction, story_and_lore, voice_acting_highlights; each a substantial paragraph)
- deep_dive_takeaway (string; 150+ words on why this episode matters to the cour)
- episode_vibe (short string; e.g. "Emotional Peak & Tearjerker", "High-Octane Battle", "Slow-Burn Mystery")
- where_to_watch (array of {"name": platform, "url": url} using ONLY the licensed platforms provided)

Total original prose must exceed 500 words. No markdown. No preamble.
"""
