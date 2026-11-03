local m_str_utils = require("Module:string utilities")

local codepoint = m_str_utils.codepoint
local concat = table.concat
local explode_chars = require("Module:Hani").explode_chars
local find = m_str_utils.find
local format = string.format
local gmatch = m_str_utils.gmatch
local gsub = m_str_utils.gsub
local insert = table.insert
local ipairs = ipairs
local match = m_str_utils.match
local pairs = pairs
local split = m_str_utils.split
local gsplit = m_str_utils.gsplit

local export = {}

local hanzi = require("Module:scripts").getByCode("Hani"):getCharacters()
local bopomofo = require("Module:scripts").getByCode("Bopo"):getCharacters()

local langname = {
	["cdo"] = "Eastern Min",
	["cjy"] = "Jin",
	["cpx"] = "Puxian Min",
	["cmn"] = "Mandarin",
	["csp"] = "Southern Pinghua",
	["dng"] = "Dungan",
	["gan"] = "Gan",
	["hak"] = "Hakka",
	["hsn"] = "Xiang",
	["hsn-lou"] = "Xiang",
	["hsn-hya"] = "Xiang",
	["luh"] = "Leizhou Min",
	["mnp"] = "Northern Min",
	["nan-hbl"] = "Hokkien",
	["nan-tws"] = "Teochew",
	["wuu"] = "Wu",
	["wuu-jih"] = "Wu",
	["yue"] = "Cantonese",
	["zhx-sic"] = "Sichuanese",
	["zhx-tai"] = "Taishanese",
}

local langname_abbr = {
	["m"] = "Mandarin",
	["m-s"] = "Sichuanese",
	["m-x"] = "Mandarin",
	["m-nj"] = "Mandarin",
	["dg"] = "Dungan",
	["c"] = "Cantonese",
	["c-dg"] = "Cantonese",
	["c-t"] = "Taishanese",
	["c-yj"] = "Cantonese",
	["g"] = "Gan",
	["h"] = "Hakka",
	["j"] = "Jin",
	["mb"] = "Northern Min",
	["mc"] = "Middle Chinese",
	["md"] = "Eastern Min",
	["mn"] = "Hokkien",
	["mn-t"] = "Teochew",
	["mn-l"] = "Leizhou Min",
	["oc"] = "Old Chinese",
	["px"] = "Puxian Min",
	["sp"] = "Southern Pinghua",
	["w"] = "Wu",
	["w-j"] = "Wu",
	["x"] = "Xiang",
	["x-l"] = "Loudi Xiang",
	["x-h"] = "Hengyang Xiang",
}

local pos_aliases_cat = {
	["n"] = "nouns", ["noun"] = "nouns",
	["pn"] = "proper nouns", ["propn"] = "proper nouns", ["proper"] = "proper nouns", ["proper noun"] = "proper nouns",
	["pron"] = "pronouns", ["pronoun"] = "pronouns",
	["v"] = "verbs", ["verb"] = "verbs",
	["a"] = "adjectives", ["adj"] = "adjectives", ["adjective"] = "adjectives",
	["adv"] = "adverbs", ["adverb"] = "adverbs",
	["prep"] = "prepositions", ["pre"] = "prepositions",
	["postp"] = "postpositions", ["post"] = "postpositions",
	["con"] = "conjunctions", ["conj"] = "conjunctions", ["conjunction"] = "conjunctions",
	["part"] = "particles", ["particle"] = "particles",
	["pref"] = "prefixes", ["prefix"] = "prefixes",
	["suf"] = "suffixes", ["suffix"] = "suffixes",
	["infix"] = "infixes",
	["prov"] = "proverbs", ["proverb"] = "proverbs",
	["id"] = "idioms", ["idiom"] = "idioms",
	["ch"] = "chengyu", ["cy"] = "chengyu", ["4ci"] = "chengyu",
	["ph"] = "phrases", ["phrase"] = "phrases",
	["int"] =  "interjections", ["intj"] = "interjections", ["interj"] = "interjections", ["interjection"] = "interjections",
	["cl"] = "classifiers", ["cls"] = "classifiers", ["classifier"] = "classifiers",
	["num"] = "numerals", ["numeral"] = "numerals",
	["abb"] = "abbreviations", ["abbreviation"] = "abbreviations",
	["det"] = "determiners", ["deter"] = "determiners", ["determiner"] = "determiners",
	["syl"] = "syllables", ["syll"] = "syllables", ["syllable"] = "syllables",
}

local function make_note(text)
	if find(text, ": ") then
		text = "\n*" .. gsub(gsub(text, "\n", ".\n*"), "([:;]) ", "%1\n**")
	elseif find(text, "; ") then
		text = "\n*" .. gsub(text, "; ", ";\n*")
	end
	text = gsub(text, "“([^”]+)”", function (a) return "“" .. gsub(a, ";\n%*+", "; ") .. "”" end)
	-- fix bug about indentation levels (see https://en.wiktionary.org/w/index.php?oldid=78848651)
	local last_level = ("\n"..text):match("\n(%**)[^*\n][^\n]*$")
	local append = last_level:gsub("%*","<ul>")
	return "\n<div style=\"border: 1px solid var(--wikt-palette-forestgreen, #235923); padding: 4px; margin: 8px; background: var(--wikt-palette-lightyellow, #ffffe0); font-size: 85%\">'''Note''': " .. text .. ".</div>" .. append
end

local function ipa_format(text)
	local numbers = { ["1"]="¹",["2"]="²",["3"]="³",["4"]="⁴",["5"]="⁵",["0"]="⁰",["-"]="⁻",["/"]="/, /" }
	return gsub(text,"[0-5%-/]",numbers)
end

local function Consolas(text)
	return '<span class="zhpron-monospace">' .. text .. "</span>"
end

local function format_IPA(text)
	return '<span class="IPA">' .. text .. "</span>"
end

function export.make(frame)
	local parent_args = frame:getParent().args
	local params = {
		pagename = {},
		namespace = {},
		dial = {},
		mc = {},
		oc = {},
		cat = {},
		only_cat = {type = "boolean"},
		poj_form_zh_see = {type = "boolean"},
	}
	for abbr, _ in pairs(langname_abbr) do
		params[abbr] = {}
		params[abbr .. "a"] = {list = true}
		params[abbr .. "_note"] = {}
	end
	local args = require("Module:parameters").process(parent_args, params, nil, "zh-pron", "make")

	local pagename = args.pagename or mw.loadData("Module:headword/data").pagename
	local sortkey = (require("Module:Hani-sortkey").makeSortKey(pagename))
	local is_single_hanzi = find(pagename, "^[" .. hanzi .. "]$") ~= nil
	local namespace = args.namespace or mw.title.getCurrentTitle().nsText
	local m_rom = args["m"]
	local m_s_rom = args["m-s"]
	local m_x_rom = args["m-x"]
	local m_nj_rom = args["m-nj"]
	local dg_rom = args["dg"]
	local c_rom = args["c"]
	local c_dg_rom = args["c-dg"]
	local c_t_rom = args["c-t"]
	local c_yj_rom = args["c-yj"]
	local g_rom = args["g"]
	local h_rom = args["h"]
	local j_rom = args["j"]
	local mb_rom = args["mb"]
	local md_rom = args["md"]
	local mn_rom = args["mn"]
	local mn_l_rom = args["mn-l"]
	local mn_t_rom = args["mn-t"]
	local px_rom = args["px"]
	local sp_rom = args["sp"]
	local w_rom = args["w"]
	local w_j_rom = args["w-j"]
	local x_rom = args["x"]
	local x_l_rom = args["x-l"]
	local x_h_rom = args["x-h"]
	local m_audio = args["ma"]
	local m_s_audio = args["m-sa"]
	local m_x_audio = args["m-xa"]
	local m_nj_audio = args["m-nja"]
	local dg_audio = args["dga"]
	local c_audio = args["ca"]
	local c_dg_audio = args["c-dga"]
	local c_t_audio = args["c-ta"]
	local c_yj_audio = args["c-yja"]
	local g_audio = args["ga"]
	local h_audio = args["ha"]
	local j_audio = args["ja"]
	local mb_audio = args["mba"]
	local md_audio = args["mda"]
	local mn_audio = args["mna"]
	local mn_l_audio = args["mn-la"]
	local mn_t_audio = args["mn-ta"]
	local px_audio = args["pxa"]
	local sp_audio = args["spa"]
	local w_audio = args["wa"]
	local w_j_audio = args["w-ja"]
	local x_audio = args["xa"]
	local x_l_audio = args["x-la"]
	local x_h_audio = args["x-ha"]
	local dial = args["dial"]
	local mc = args["mc"]
	local oc = args["oc"]
	local only_cat = args["only_cat"]

	-- True if arguments exist for the specified variety, using a language param abbreviation.
	local function has_var(var)
		return args[var] or #args[var .. "a"] > 0
	end

	local function add_audio(text, audios, lang, show)
		-- This function has side effects
		for _, audio in ipairs(audios) do
			if audio == "y" then audio = format("%s-%s.ogg", lang, pagename) end
			insert(text, "\n*" .. (show and "::" or "**") .. " [[File:")
			insert(text, audio)
			insert(text, "]]")
		end
		if #audios > 0 then
			insert(text, "[[Category:")
			insert(text, langname[lang])
			insert(text, " terms with audio pronunciation|" .. sortkey .. "]]")
		end
	end
	
	local function add_audio_show(text, audios, lang)
		add_audio(text, audios, lang, "show")
	end

	local text = {} --the pronunciation table
	if not only_cat then
		--The whole table consists of 4 parts
		--"textShow" contains Part 1, 3 and 4
		local textShow = {'<div class="standard-box zhpron" style="overflow:auto; max-width:500px; font-size:100%">'}
		--"textHide" is Part 2
		local textHide = {}
		local function show(txt)
			insert(textShow, txt)
		end
		local function hide(txt)
			insert(textHide, txt)
		end
		local function hide_note(var)
			local note = args[var .. "_note"]
			if note then hide(make_note(note)) end
		end

		show('<div class="vsSwitcher" data-toggle-category="pronunciations">')
		--Part 1 and 2, "Pronunciation" and "Pronunciation expressed in different romanizations"
		if m_rom or m_s_rom or m_x_rom or m_nj_rom or dg_rom then
			show("\n* [[w:Mandarin Chinese|Mandarin]]")
		end
		if has_var("m") then
			local m_args = {}
			local m_pron = require("Module:cmn-pron")
			if m_rom then
				local str_analysis = m_pron.str_analysis
				local other_m_vars = has_var("m-s") or has_var("m-x") or has_var("m-nj") or has_var("dg")
				show("\n" .. str_analysis(m_rom, "head", other_m_vars))

				m_args[1] = str_analysis(m_rom, "")
				for i = 2, 5 do
					m_args[i] = str_analysis(m_rom, tostring(i))
				end
				local m_args_params_prefixed_with_1 = {"n", "na", "nb", "nc", "nd"}
				for _, base in ipairs(m_args_params_prefixed_with_1) do
					for i = 1, 5 do
						local param = tostring(i) .. base
						m_args[param] = str_analysis(m_rom, param)
					end
				end
				local m_args_params = {"py", "cap", "tl", "tl2", "tl3", "a", "audio", "er", "ertl", "ertl2", "ertl3",
					"era", "eraudio"}
				for _, base in ipairs(m_args_params) do
					m_args[base] = str_analysis(m_rom, base)
					for i = 2, 5 do
						local param = tostring(i) .. base
						m_args[param] = str_analysis(m_rom, param)
					end
				end
			end
			for i, audio in ipairs(m_audio) do
				local ind = i == 1 and "" or tostring(i)
				m_args[ind .. "a"] = audio
			end
			show(m_pron.make_audio(m_args))
			hide(m_pron.make_args(m_args))
			hide_note("m")
		end
		if (not m_rom) and (m_s_rom or m_x_rom or m_nj_rom or dg_rom) then
			hide("\n* [[w:Mandarin Chinese|Mandarin]]")
		end
		if has_var("m-s") then
			local m_s_pron = require("Module:zhx-sic-pron")
			-- ȵ [[Wiktionary talk:Chinese entry guidelines/Sichuanese#"ny"]]
			local m_s_processed = gsub(m_s_rom:gsub("/", " / "), "([%d-])([%a])", "%1 %2")
				:gsub("%d[%d%*%-]*%f[^%d%*]", "<sup>%0</sup>")
				:gsub("ny", "ȵ")
			if m_s_rom then
				show("\n*: <small>(<i>[[w:Sichuanese dialect|Chengdu]], [[w:Sichuanese Pinyin|Sichuanese Pinyin]]</i>)</small>: ")
				show(Consolas(m_s_processed))
			end
			add_audio_show(textShow, m_s_audio, "zhx-sic")
			hide("\n** <small>(<i>[[w:Chengdu|Chengdu]]</i>)</small>")
			hide("\n*** <small><i>[[w:Sichuanese Pinyin|Sichuanese Pinyin]]</i></small>: ")
			hide(Consolas(m_s_processed))
			local xinwenz = m_s_pron.convert(m_s_rom, "SWZ")
			if xinwenz then
				hide("\n*** <small><i>[[w:zh:四川话拉丁化新文字|Scuanxua Ladinxua Xin Wenz]]</i></small>: ")
				hide(Consolas(m_s_pron.convert(m_s_rom, "SWZ")))
			end
			hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:zh:成都话|key]])</sup></small>: ")
			hide(format_IPA(m_s_pron.convert(m_s_rom, "IPA")))
			hide_note("m-s")
		end
		if has_var("m-x") then
			local m_x_pron = require("Module:cmn-pron-Xian")
			local m_x_display, m_x_hidden, m_x_ipa = m_x_pron.py_process(m_x_rom)
			show("\n*: <small>(<i>[[w:Guanzhong dialect|Xi'an]], [[Wiktionary:About Chinese/Xi'an|Guanzhong Pinyin]]</i>)</small>: ")
			show(Consolas(m_x_display))
			add_audio_show(textShow, m_x_audio, "cmn")
			hide("\n** <small>(<i>[[w:Xi'an|Xi'an]]</i>)</small>")
			hide("\n*** <small><i>[[Wiktionary:About Chinese/Xi'an|Guanzhong Pinyin]]</i></small>: ")
			hide(Consolas(m_x_hidden))
			hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:Guanzhong dialect|key]])</sup></small>: ")
			hide(format_IPA(m_x_ipa))
			hide_note("m-x")
		end
		if has_var("m-nj") then
			local m_nj_pron = require("Module:cmn-pron-Nanjing")
			local m_nj_display, m_nj_hidden, m_nj_num, m_nj_ipa = m_nj_pron.py_process(m_nj_rom)
			show("\n*: <small>(<i>[[w:Nanjing dialect|Nanjing]], [[Wiktionary:About Chinese/Nanjing|Nanjing Pinyin]]</i>)</small>: ")
			show(Consolas(m_nj_display))
			add_audio_show(textShow, m_nj_audio, "cmn")
			hide("\n** <small>(<i>[[w:Nanjing|Nanjing]]</i>)</small>")
			hide("\n*** <small><i>[[Wiktionary:About Chinese/Nanjing|Nanjing Pinyin]]</i></small>: ")
			hide(Consolas(m_nj_hidden))
			hide("\n*** <small><i>[[Wiktionary:About Chinese/Nanjing|Nanjing Pinyin]] (numbered)</i></small>: ")
			hide(Consolas(m_nj_num))
			hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:Nanjing dialect|key]])</sup></small>: ")
			hide(format_IPA(m_nj_ipa))
			hide_note("m-nj")
		end
		if has_var("dg") then
			local dg_pron = require("Module:dng-pron")
			local dg_processed = dg_pron.process(dg_rom)
			if dg_rom then
				show("\n*: <small>(<i>[[w:Dungan language|Dungan]], [[w:Dungan alphabet|Cyrillic]] and [[Wiktionary:Dungan transliteration|Wiktionary]]</i>)</small>: ")
				show(Consolas(dg_processed))
			end
			add_audio_show(textShow, dg_audio, "dng")
			hide("\n** <small>(<i>[[w:Dungan language|Dungan]]</i>)</small>")
			hide("\n*** <small><i>[[w:Dungan alphabet|Cyrillic]] and [[Wiktionary:Dungan transliteration|Wiktionary]]</i></small>: ")
			hide(Consolas(dg_processed))
			hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:Dungan phonology|key]])</sup></small>: ")
			hide(format_IPA(dg_pron.convert(dg_rom, "IPA")) .. "\n**: <small>(Note: Dungan pronunciation is currently experimental and may be inaccurate.)</small>")
			hide_note("dg")
		end
		if has_var("c") or has_var("c-dg") or has_var("c-t") or has_var("c-yj") then
			if c_rom or c_dg_rom or c_t_rom or c_yj_rom then
				local c_count = (c_rom and 1 or 0) + (c_dg_rom and 1 or 0)
					+ (c_t_rom and 1 or 0) + (c_yj_rom and 1 or 0)
				local c_sep = (c_count == 1) and " " or "\n*: "
				show("\n* [[w:Cantonese|Cantonese]]")
				hide("\n* [[w:Cantonese|Cantonese]]")
				if c_rom then
					local c_pron = require("Module:yue-pron")
					show(c_sep)
					show("<small>(<i>")
					if c_count > 1 then
						show("[[w:Guangzhou Cantonese|Guangzhou]]–[[w:Hong Kong Cantonese|Hong Kong]], ")
					end
					show("[[w:Jyutping|Jyutping]]</i>)</small>: ")
					show(Consolas(c_pron.show_standard(c_rom, is_single_hanzi)))
					add_audio_show(textShow, c_audio, "yue")
					hide(c_pron.hide_standard(c_rom, is_single_hanzi))
					if not args["c_note"] and is_single_hanzi and (c_rom:find("^[ao]") or c_rom:find(",[ao]")) then
						args["c_note"] = "The zero initial " .. format_IPA("/∅-/") .. " is commonly pronounced with a ''ng''-initial " .. format_IPA("/ŋ-/") .. " in some varieties of Cantonese, including Hong Kong Cantonese"
					end
					hide_note("c")
				end
				if c_dg_rom then
					local c_dg_pron = require("Module:yue-pron/Dongguan")
					local c_dg_display = c_dg_rom:gsub(","," / ")
						:gsub("%d[%d%*%-]*%f[^%d%*]", "<sup>%0</sup>")
					show(c_sep .. "<small>(<i>[[w:zh:東莞話|Dongguan]], [[Wiktionary:About Chinese/Cantonese/Dongguan|Jyutping++]]</i>)</small>: ")
					show(Consolas(c_dg_display))
					add_audio_show(textShow, c_dg_audio, "yue")
					hide("\n** <small>(<i>[[w:zh:東莞話|Dongguan]], [[w:Guancheng Subdistrict|Guancheng]]</i>)</small>")
					hide("\n*** <small><i>[[Wiktionary:About Chinese/Cantonese/Dongguan|Jyutping++]]</i></small>: ")
					hide(Consolas(c_dg_display))
					hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:zh:東莞話|key]])</sup></small>: ")
					hide(format_IPA(c_dg_pron.jpp_to_ipa(c_dg_rom)))
					hide_note("c-dg")
				end
				if c_t_rom then
					local c_t_pron = require("Module:yue-pron/Taishanese")
					local c_t_display = c_t_rom:gsub(","," / ")
						:gsub("%d[%d%*%-]*%f[^%d%*]", "<sup>%0</sup>")
					show(c_sep .. "<small>(<i>[[w:Taishanese|Taishan]], [[Wiktionary:About Chinese/Cantonese/Taishanese|Wiktionary]]</i>)</small>: ")
					show(Consolas(c_t_display))
					add_audio_show(textShow, c_t_audio, "zhx-tai")
					hide("\n** <small>(<i>[[w:Taishanese|Taishanese]], [[w:Taicheng Subdistrict|Taicheng]]</i>)</small>")
					hide("\n*** <small><i>[[Wiktionary:About Chinese/Cantonese/Taishanese|Wiktionary]]</i></small>: ")
					hide(Consolas(c_t_display))
					hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:Taishanese|key]])</sup></small>: ")
					hide(format_IPA(c_t_pron.hoisanva_to_ipa(c_t_rom)))
					hide_note("c-t")
				end
				if c_yj_rom then
					local c_yj_pron = require("Module:yue-pron/Yangjiang")
					local c_yj_display = c_yj_rom:gsub(","," / ")
						:gsub("%d[%d%*%-]*%f[^%d%*]", "<sup>%0</sup>")
					show(c_sep .. "<small>(<i>[[w:zh:陽江話|Yangjiang]], [[Wiktionary:About Chinese/Cantonese/Yangjiang|Jyutping++]]</i>)</small>: ")
					show(Consolas(c_yj_display))
					add_audio_show(textShow, c_yj_audio, "yue")
					hide("\n** <small>(<i>[[w:zh:陽江話|Yangjiang Yue]], [[w:Jiangcheng, Yangjiang|Jiangcheng]]</i>)</small>")
					hide("\n*** <small><i>[[Wiktionary:About Chinese/Cantonese/Yangjiang|Jyutping++]]</i></small>: ")
					hide(Consolas(c_yj_display))
					hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:Gao–Yang Yue|key]])</sup></small>: ")
					hide(format_IPA(c_yj_pron.jpp_to_ipa(c_yj_rom)))
					hide_note("c-yj")
				end
			end
		end
		if has_var("g") then
			local g_pron = require("Module:gan-pron")
			if g_rom then
				show("\n* [[w:Gan Chinese|Gan]] <small>(<i>[[Wiktionary:About Chinese/Gan|Wiktionary]]</i>)</small>: ")
				show(Consolas(g_pron.rom(g_rom)))
			end
			add_audio_show(textShow, g_audio, "gan")
			hide("\n* [[w:Gan Chinese|Gan]]")
			hide("\n** <small>(<i>[[w:Nanchang dialect|Nanchang]]</i>)</small>")
			hide("\n*** <small><i>[[Wiktionary:About Chinese/Gan|Wiktionary]]</i></small>: ")
			hide(Consolas(g_pron.rom(g_rom)))
			hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:Nanchang dialect|key]])</sup></small>: ")
			hide(format_IPA("/" .. g_pron.ipa(g_rom) .. "/"))
			hide_note("g")
		end
		if h_rom and (find(h_rom, "pfs=.") or find(h_rom, "gd=.") or find(h_rom, "hrs=.") or find(h_rom, "ct=.")) or #h_audio > 0 then
			local h_pron = require("Module:hak-pron")
			if find(h_rom, "pfs=.") or find(h_rom, "gd=.") or find(h_rom, "hrs=.") or find(h_rom, "ct=.") then
				show("\n* [[w:Hakka Chinese|Hakka]]")
				show(h_pron.rom_display(h_rom,"yes"))
			end
			add_audio_show(textShow, h_audio, "hak")
			hide("\n* [[Wiktionary:About Chinese/Hakka|Hakka]]")
			if h_rom then hide(h_pron.rom_display(h_rom,"")) end
			hide_note("h")
		end
		if has_var("j") then
			local j_pron = require("Module:cjy-pron")
			if j_rom then
				show("\n* [[w:Jin Chinese|Jin]] <small>(<i>[[Wiktionary:About Chinese/Jin|Wiktionary]]</i>)</small>: ")
				show(Consolas(j_pron.rom(j_rom)))
			end
			add_audio_show(textShow, j_audio, "cjy")
			hide("\n* [[w:Jin Chinese|Jin]]")
			hide("\n** <small>(<i>[[w:Taiyuan|Taiyuan]]</i>)<sup>[[:w:zh:太原話|+]]</sup></small>")
			if j_rom then
				hide("\n*** <small><i>[[Wiktionary:About Chinese/Jin|Wiktionary]]</i></small>: ")
				hide(Consolas(j_pron.rom(j_rom)))
			end
			local no_sandhi = false
			local roms = split(j_rom, "/")
			for i = 1, #roms do
				if find(roms[i], " [^ ]+ ") then
					no_sandhi = true
					break
				end
			end
			hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] (<i>old-style" .. (no_sandhi and ", no sandhi" or "") .. "</i>)</small>: ")
			hide(format_IPA("/" .. j_pron.ipa(j_rom, no_sandhi and "no_sandhi" or "") .. "/"))
			hide_note("j")
		end
		if has_var("mb") then
			local mb_pron = require("Module:mnp-pron")
			if mb_rom then
				show("\n* [[w:Northern Min|Northern Min]] <small>(<i>[[w:Kienning Colloquial Romanized|KCR]]</i>)</small>: ")
				show(Consolas(mb_pron.rom(mb_rom)))
			end
			add_audio_show(textShow, mb_audio, "mnp")
			hide("\n* [[w:Northern Min|Northern Min]]")
			hide("\n** <small>(<i>[[w:Jian'ou dialect|Jian'ou]]</i>)</small>")
			if mb_rom then
				hide("\n*** <small><i>[[w:Kienning Colloquial Romanized|Kienning Colloquial Romanized]]</i></small>: ")
				hide(Consolas(mb_pron.rom(mb_rom)))
				hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:Jian'ou dialect|key]])</sup></small>: ")
				hide(format_IPA(mb_pron.ipa(mb_rom)))
			end
			hide_note("mb")
		end
		if has_var("md") then
			local md_pron = require("Module:cdo-pron")
			if md_rom then
				show("\n* [[w:Eastern Min|Eastern Min]] <small>(<i>[[Wiktionary:About Chinese/Eastern Min|BUC]]</i>)</small>: ")
				show(Consolas(md_pron.rom(md_rom)))
			end
			add_audio_show(textShow, md_audio, "cdo")
			hide("\n* [[w:Eastern Min|Eastern Min]]")
			hide("\n** <small>(<i>[[w:Fuzhou dialect|Fuzhou]]</i>)</small>")
			if md_rom then
				hide("\n*** <small><i>[[Wiktionary:About Chinese/Eastern Min|Bàng-uâ-cê]]</i></small>: ")
				hide(Consolas(md_pron.rom(md_rom)))
				if not (md_rom and find(md_rom, "([^/]*)-([^/]*)-([^/]*)-([^/]*)-([^/]*)")) then
					hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:Fuzhou dialect|key]])</sup></small>: ")
					hide(format_IPA("/" .. md_pron.ipa(md_rom) .. "/"))
				else
					hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:Fuzhou dialect|key]])</sup> (<i>no sandhi</i>)</small>: ")
					hide(format_IPA("/" .. md_pron.ipa(md_rom, "no_sandhi") .. "/"))
				end
			end
			hide_note("md")
		end
		if has_var("px") then
			local px_pron = require("Module:cpx-pron")
			show("\n* [[w:Puxian Min|Puxian Min]]")
			show(px_pron.rom_display(px_rom,"brief"))
			add_audio_show(textShow, px_audio, "cpx")
			hide("\n* [[Wiktionary:About Chinese/Puxian Min|Puxian Min]]")
			if px_rom then hide(px_pron.rom_display(px_rom,"complete")) end
			hide_note("px")
		end
		if has_var("mn") or has_var("mn-l") or has_var("mn-t") then
			local mn_pron, mn_l_pron
			if has_var("mn") or has_var("mn-t") then
				mn_pron = require("Module:nan-pron")
			end
			if has_var("mn-l") then
				mn_l_pron = require("Module:luh-pron")
			end
			
			if mn_rom or mn_t_rom or mn_l_rom then
				show("\n* [[w:Southern Min|Southern Min]]")
				if mn_rom then
					show(((mn_l_rom or mn_t_rom) and "\n*:" or "") .. " <small>(<i>[[w:Hokkien|Hokkien]], [[w:Pe̍h-ōe-jī|POJ]]</i>)</small>: ")
					show(Consolas(mn_pron.poj_display(mn_pron.poj_check_invalid(mn_rom))))
					add_audio_show(textShow, mn_audio, "nan-hbl")
				end
				if mn_t_rom then
					show(((mn_rom or mn_l_rom) and "\n*:" or "") .. " <small>(<i>[[w:Teochew dialect|Teochew]], [[w:Peng'im|Peng'im]]</i>)</small>: ")
					show(Consolas(mn_pron.pengim_display(mn_t_rom)))
					add_audio_show(textShow, mn_t_audio, "nan-tws")
				end
				if mn_l_rom then
					show(((mn_rom or mn_t_rom) and "\n*:" or "") .. " <small>(<i>[[w:Leizhou Min|Leizhou]], Leizhou Pinyin</i>)</small>: ")
					show(Consolas(mn_l_pron.rom(mn_l_rom)))
					add_audio_show(textShow, mn_l_audio, "luh")
				end
			end
			hide("\n* [[w:Southern Min|Southern Min]]")
			if has_var("mn") then
				hide(mn_pron.generate_all(mn_rom))
				hide_note("mn")
			end
			if has_var("mn-t") then
				hide("\n** <small>(<i>[[w:Teochew dialect|Teochew]]</i>)</small>")
				hide("\n*** <small><i>[[w:Peng'im|Peng'im]]</i></small>: ")
				hide(Consolas(mn_pron.pengim_display(mn_t_rom)))
				hide("\n*** <small><i>[[w:Pe̍h-ōe-jī|Pe̍h-ōe-jī]]-like</i></small>: ")
				hide(Consolas(mn_pron.pengim_to_pojlike_conv(mn_t_rom)))
				hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:zh:潮州話#語音|key]])</sup></small>: ")
				hide(format_IPA(mn_pron.pengim_to_ipa_conv(mn_t_rom)))
				hide_note("mn-t")
			end
			if has_var("mn-l") then
				hide("\n** <small>(<i>[[w:Leizhou Min|Leizhou]]</i>)</small>")
				hide("\n*** <small><i>Leizhou Pinyin</i></small>: ")
				hide(Consolas(mn_l_pron.rom(mn_l_rom)))
				hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]]</small>: ")
				hide(format_IPA(mn_l_pron.ipa(mn_l_rom)))
				hide_note("mn-l")
			end
		end
		if has_var("sp") then
			local sp_pron = require("Module:csp-pron")
			local sp_processed = sp_rom:gsub(",([^ ])",", %1")
				:gsub("%d[%d%*%-]*%f[^%d%*]", "<sup>%0</sup>")
			show("\n* [[w:Pinghua|Southern Pinghua]] <small>(<i>[[w:Pinghua|Nanning]], [[Wiktionary:About Chinese/Southern Pinghua|Jyutping++]]</i>)</small>: ")
			show(Consolas(sp_processed))
			add_audio_show(textShow, sp_audio, "csp")
			hide("\n* [[w:Pinghua|Southern Pinghua]]")
			hide("\n** <small>(<i>[[w:Pinghua|Nanning Pinghua]], [[w:Nanning|Tingzi]]</i>)</small>")
			hide("\n*** <small><i>[[Wiktionary:About Chinese/Southern Pinghua|Jyutping++]]</i></small>: ")
			hide(Consolas(sp_processed))
			hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:Pinghua#Phonology|key]])</sup></small>: ")
			hide(format_IPA(sp_pron.jpp_to_ipa(sp_rom)))
			hide_note("sp")
		end
		if has_var("w") or has_var("w-j") then
			local w_count = (w_rom and 1 or 0) + (w_j_rom and 1 or 0)
			local w_show, w_hide, w_j_show, w_j_hide
			if w_rom then
				w_show, w_hide = require("Module:wuu-pron").make(w_rom, w_count)
			end
			if w_j_rom then
				w_j_show, w_j_hide = require("Module:wuu-pron/Jinhua").make(w_j_rom, w_count)
			end
			if w_count > 1 then
				show("\n* [[w:Wu Chinese|Wu]] <small>(<i>[[Wiktionary:About Chinese/Wu|Wugniu]]</i>)</small>")
			else
				show("\n* [[w:Wu Chinese|Wu]]")
			end
			show(w_show)
			show(w_j_show)
			add_audio_show(textShow, w_audio, "wuu")
			hide("\n* [[w:Wu Chinese|Wu]]")
			hide(w_hide)
			hide(w_j_hide)
			-- add_audio(textHide, w_audio, "wuu")
			hide_note("w")
			hide_note("w-j")
		end
		if has_var("x") or has_var("x-l") or has_var("x-h") then
			local x_pron = has_var("x") and require("Module:hsn-pron") or nil
			local x_l_pron = has_var("x-l") and require("Module:hsn-pron-Loudi") or nil
			local x_h_pron = has_var("x-h") and require("Module:hsn-pron-Hengyang") or nil
			if x_rom or x_l_rom or x_h_rom then
				show("\n* [[w:Xiang Chinese|Xiang]]")
				if x_rom then
					show(((x_l_rom or x_h_rom) and "\n*:" or "") .. " <small>(<i>[[w:Changsha dialect|Changsha]], [[Wiktionary:About Chinese/Xiang|Wiktionary]]</i>)</small>: ")
					show(Consolas(x_pron.rom(x_rom)))
					add_audio_show(textShow, x_audio, "hsn")
				end
				if x_l_rom then
					show(((x_rom or x_h_rom) and "\n*:" or "") .. " <small>(<i>[[w:zh:娄底话|Loudi]], [[Wiktionary:About Chinese/Xiang/Loudi|Wiktionary]]</i>)</small>: ")
					show(Consolas(x_l_pron.rom(x_l_rom)))
					add_audio_show(textShow, x_l_audio, "hsn-lou")
				end
				if x_h_rom then
					show(((x_rom or x_l_rom) and "\n*:" or "") .. " <small>(<i>[[w:Hengyang dialect|Hengyang]], [[Wiktionary:About Chinese/Xiang/Hengyang|Wiktionary]]</i>)</small>: ")
					show(Consolas(x_h_pron.rom(x_h_rom)))
					add_audio_show(textShow, x_h_audio, "hsn-hya")
				end
			end
			hide("\n* [[w:Xiang Chinese|Xiang]]")
			if x_rom then
				local x_diff = x_pron.stylediff(x_rom)
				hide("\n** <small>(<i>[[w:Changsha dialect|Changsha]]</i>)</small>")
				hide("\n*** <small><i>[[Wiktionary:About Chinese/Xiang|Wiktionary]]</i></small>: ")
				hide(Consolas(x_pron.rom(x_rom)))
				hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:Changsha dialect|key]])</sup>")
				hide(x_diff and " (<i>old-style</i>)" or "")
				hide("</small>: ")
				hide(format_IPA("/" .. x_pron.ipa(x_rom) .. "/"))
				if x_diff then
					hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:Changsha dialect|key]])</sup> (<i>new-style</i>)</small>: ")
					hide(format_IPA("/" .. x_pron.ipa(x_rom, "new") .. "/"))
				end
				hide_note("x")
			end
			if x_l_rom then
				hide("\n** <small>(<i>[[w:zh:娄底话|Loudi]]</i>)</small>")
				hide("\n*** <small><i>[[Wiktionary:About Chinese/Xiang/Loudi|Wiktionary]]</i></small>: ")
				hide(Consolas(x_l_pron.rom(x_l_rom)))
				hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:zh:娄底话|key]])</sup>")
				hide("</small>: ")
				hide(format_IPA("/" .. x_l_pron.ipa(x_l_rom) .. "/"))
				hide_note("x-l")
			end
			if x_h_rom then
				hide("\n** <small>(<i>[[w:Hengyang dialect|Hengyang]]</i>)</small>")
				hide("\n*** <small><i>[[Wiktionary:About Chinese/Xiang/Hengyang|Wiktionary]]</i></small>: ")
				hide(Consolas(x_h_pron.rom(x_h_rom)))
				hide("\n*** <small>Sinological [[Wiktionary:International Phonetic Alphabet|IPA]] <sup>([[w:Hengyang dialect|key]])</sup>")
				hide("</small>: ")
				hide(format_IPA("/" .. x_h_pron.ipa(x_h_rom) .. "/"))
				hide_note("x-h")
			end
		end
		-- combine textShow and textHide into text
		text = {
			concat(textShow),
			'<span class="vsToggleElement" style="float: right;"></span>\n<div class="vsHide" style="clear:right;">\n<hr>\n',
			concat(textHide),
			"</div></div>"
		}

		--Part 3 "Dialectal data"
		if dial ~= "n" and is_single_hanzi then
			local success, m_dial = pcall(mw.loadData, "Module:zh/data/dial-pron/" .. pagename)
			if success then
				local dialPron = {}
				local temporary = {}
				if dial and find(dial, "^[0-9\\,]+$") then
					for element in gsplit(dial, ",") do
						insert(dialPron, m_dial[tonumber(element)])
					end
				else
					for _, element in ipairs(m_dial) do
						insert(dialPron, element)
					end
				end
				for _, set in ipairs(dialPron) do
					for _, object in ipairs(set[2]) do
						insert(temporary, object)
					end
				end

				insert(text,
					'\n<hr style="clear:right;">\n<div class="vsSwitcher" data-toggle-category="pronunciations" style="background-color:var(--wikt-palette-palergreen, #F8FFFA)">\n* ' ..
					'Dialectal data' ..
					'<span class="vsToggleElement" style="float:right; padding:0 0"></span>\n' ..
					'<div class="vsHide">'
				)

				insert(text, '\n{| class="wikitable" ' ..
					'" style="width:100%; margin:0; ' ..
					'text-align:center; border-collapse: collapse; border-style: hidden; display: table;"')

				local locStart = "\n|-\n!"
				local readingStart = concat({'\n!style="background:var(--wikt-palette-indigo-3, #e0defa); width:9em"|',
				'<div style="float: right; clear: right; font-size:60%"><span class="plainlinks">[', tostring(mw.uri.fullUrl("Module:zh/data/dial-pron/" .. pagename, {["action"]="edit"})), ' edit]</span></div><span lang="zh" class="Hani">'})
				local locEnd = '<span class="IPA">'
				local headclr = 'style="background:var(--wikt-palette-indigo-3, #e0defa)"|'
				
				-- NOTE:
				-- These colours are duplicated in [[Module:zh-dial-syn]]. 
				-- Make sure the two lists are kept in sync.
				local mandarinColor = 'style="background:var(--wikt-palette-grey-amber-1, #FCFAF5)"|'
				local jinColor = 'style="background:var(--wikt-palette-grey-orange-1, #F9F0E8)"|'
				local wuColor = 'style="background:var(--wikt-palette-grey-purple-1, #F5F0FC)"|'
				local huiColor = 'style="background:var(--wikt-palette-grey-yellow-1, #FCFAF5)"|'
				local xiangColor = 'style="background:var(--wikt-palette-grey-blue-1, #ECF2FC)"|'
				local ganColor = 'style="background:var(--wikt-palette-grey-teal-1, #EAF4EF)"|'
				local hakkaColor = 'style="background:var(--wikt-palette-grey-blue-1, #ECF2FC)"|'
				local cantoneseColor = 'style="background:var(--wikt-palette-grey-cyan-1, #EBF3F5)"|'
				local minColor = 'style="background:var(--wikt-palette-grey-green-1, #EDF4EA)"|'
				
				local clrList = {
					mandarinColor, mandarinColor, mandarinColor, mandarinColor, 
					mandarinColor, mandarinColor, mandarinColor, mandarinColor, 
					mandarinColor, mandarinColor, mandarinColor, mandarinColor,
					mandarinColor, mandarinColor, mandarinColor, mandarinColor,
					mandarinColor, jinColor, jinColor, jinColor,
					wuColor, wuColor, wuColor, wuColor,
					huiColor, huiColor, xiangColor, xiangColor, 
					ganColor, hakkaColor, hakkaColor, cantoneseColor,
					cantoneseColor, cantoneseColor, minColor, minColor,
					minColor, minColor, minColor
				}
				local locList = {
					concat({headclr, "Variety\n!", headclr, "Location"}),
					concat({"rowspan=17 ", mandarinColor,  "Mandarin\n!", mandarinColor, "[[w:Beijing dialect|Beijing]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:Harbin dialect|Harbin]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:Tianjin dialect|Tianjin]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:Jinan dialect|Jinan]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:Qingdao dialect|Qingdao]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:zh:鄭州話|Zhengzhou]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:Xi'an dialect|Xi'an]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:Xining|Xining]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:Yinchuan|Yinchuan]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:zh:蘭州話|Lanzhou]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:zh:烏魯木齊話|Ürümqi]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:zh:武漢話|Wuhan]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:Chengdu dialect|Chengdu]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:zh:貴陽話|Guiyang]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:Kunming dialect|Kunming]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:Nanjing dialect|Nanjing]]\n|", mandarinColor}),
					concat({mandarinColor, "[[w:zh:合肥話|Hefei]]\n|", mandarinColor}),
					concat({"rowspan=3 ", jinColor, "Jin\n!", jinColor, "[[w:zh:太原話|Taiyuan]]\n|", jinColor}),
					concat({jinColor, "[[w:Pingyao|Pingyao]]\n|", jinColor}),
					concat({jinColor, "[[w:Hohhot dialect|Hohhot]]\n|", jinColor}),
					concat({"rowspan=4 ", wuColor, "Wu\n!", wuColor, "[[w:Shanghai dialect|Shanghai]]\n|", wuColor}),
					concat({wuColor, "[[w:Suzhou dialect|Suzhou]]\n|", wuColor}),
					concat({wuColor, "[[w:Hangzhou dialect|Hangzhou]]\n|" , wuColor}),
					concat({wuColor, "[[w:Wenzhou dialect|Wenzhou]]\n|", wuColor}),
					concat({"rowspan=2 ", huiColor, "Hui\n!", huiColor, "[[w:Shexian|Shexian]]\n|", huiColor}),
					concat({huiColor, "[[w:zh:屯溪話|Tunxi]]\n|", huiColor}),
					concat({"rowspan=2 ", xiangColor, "Xiang\n!", xiangColor, "[[w:Changsha dialect|Changsha]]\n|", xiangColor}),
					concat({xiangColor, "[[w:zh:湘潭話|Xiangtan]]\n|", xiangColor}),
					concat({ganColor, "Gan\n!", ganColor, "[[w:Nanchang dialect|Nanchang]]\n|", ganColor}),
					concat({"rowspan=2 ", hakkaColor, "Hakka\n!", hakkaColor, "[[w:Meixian dialect|Meixian]]\n|", hakkaColor}),
					concat({hakkaColor, "[[w:Taoyuan, Taiwan|Taoyuan]]\n|", hakkaColor}),
					concat({"rowspan=3 ", cantoneseColor, "Cantonese\n!", cantoneseColor, "[[w:Guangzhou dialect|Guangzhou]]\n|", cantoneseColor}),
					concat({cantoneseColor, "[[w:Nanning|Nanning]]\n|", cantoneseColor}),
					concat({cantoneseColor, "[[w:Hong Kong dialect|Hong Kong]]\n|", cantoneseColor}),
					concat({"rowspan=5 ", minColor, "Min\n!", minColor, "[[w:Xiamen dialect|Xiamen]] (Hokkien)\n|", minColor}),
					concat({minColor, "[[w:Fuzhou dialect|Fuzhou]] (Eastern Min)\n|", minColor}),
					concat({minColor, "[[w:Jian'ou dialect|Jian'ou]] (Northern Min)\n|", minColor}),
					concat({minColor, "[[w:Shantou dialect|Shantou]] (Teochew)\n|", minColor}),
					concat({minColor, "[[w:Haikou dialect|Haikou]] (Hainanese)\n|", minColor})}

				local function ipa_correct(ipa, location)
					if location == 22 then return (gsub(ipa, "13", "23")) else return ipa end
				end

				local function fmtDial(text, location)
					local fmttedPron = {}
					if text == "" then return "" end
					for pronunciation in gsplit(text, "|") do
						local ipa = match(pronunciation, "^[^%(%)" .. hanzi .. "～,]+")
						ipa = gsub(ipa, "([ptk])([0-5])", "%1̚%2")
						local environ = match(pronunciation, "[%(%)" .. hanzi .. "～,]*$") or false
						insert(fmttedPron, "<span class=\"IPA\"><small>/" ..
							tostring(ipa_format(ipa_correct(ipa, location))) .. "/</small></span>" .. (environ
							and " <span class=\"Hani\" lang=\"zh\"><small>"..environ.."</small></span>" or nil))
					end
					return concat(fmttedPron, "<br>")
				end

				for locationNo = 1, 40 do
					for readingNo = 1, #dialPron do
						if readingNo == 1 then
							insert(text, locStart)
							insert(text, locList[locationNo])
						end
						if locationNo == 1 then
							local situation = dialPron[readingNo][1]
							insert(text, readingStart)
							insert(text, pagename)
							insert(text, (pagename ~= situation and " (" ..
								gsub(situation, pagename, "<b>" .. pagename .. "</b>") .. ")" or ""))
							insert(text, "</span>")
						else
							insert(text, (readingNo == 1 and "" or "\n|" .. clrList[locationNo-1]))
							insert(text, locEnd)
							insert(text, fmtDial(dialPron[readingNo][2][locationNo-1], locationNo))
							insert(text, "</span>")
						end
					end
				end
				insert(text, "\n|}</div></div>")
			end
		end

		--Part 4 "Middle Chinese & Old Chinese"
		local mc_preview, oc_preview
		local m_ltc_pron, m_och_pron

		-- !!!
		-- The following function modifies the tables generated by mod:ltc-pron and mod:och-pron, shifting them
		-- from using "mw-collapsible" to using "vsSwitcher", because the former
		-- can not collapse on the mobile site and makes Chinese entries a mess.
		-- It is supposed to be a temporary solution.
		-- !!!
		local function shiftCustomtoggle2Vsswitcher(s)
			local result
			result = (s:gsub(
				'\n%* <div title="expand" class="mw%-customtoggle[^>]+">',
				'\n<div class="vsSwitcher" data-toggle-category="pronunciations">\n* '
			):gsub(
				'<span style="float:right; border:1px solid var%(%-%-wikt%-palette%-lightgrey,#ccc%); border%-radius:1px; padding:0 0; font%-size:90%%">▼</span>(.-)</div>\n{| class="wikitable',
				'<span class="vsToggleElement" style="float:right; padding:0 0"></span>%1\n<div class="vsHide">\n{| class="wikitable'
			):gsub(
				'{| class="wikitable mw%-collapsible mw%-collapsed" id="[^"]+"',
				'{| class="wikitable"'
			):gsub(
				"\n|}$",
				"\n|}</div></div>"
			))
			return result
		end

		if mc then
			m_ltc_pron = require("Module:ltc-pron")
			mc_preview = m_ltc_pron.retrieve_pron(pagename, false, mc, true)
			if not mc_preview then
				require("Module:debug/track")("zh-pron/Middle Chinese data not found")
				mc = nil
			end
		end
		if oc then
			m_och_pron = require("Module:och-pron")
			oc_preview = m_och_pron.generate_show(pagename, oc)
			if not oc_preview then
				require("Module:debug/track")("zh-pron/Old Chinese data not found")
				oc = nil
			end
		end
		if mc or oc then
			insert(text, '\n<hr style="clear:right;">\n<div style="background-color:var(--wikt-palette-lighterblue, #ebf4ff); margin: 0 -5px -5px; padding: 0 5px 5px;">')
			if mc then
				insert(text, shiftCustomtoggle2Vsswitcher(m_ltc_pron.ipa(mc, mc_preview)))
			end
			if oc then
				insert(text, shiftCustomtoggle2Vsswitcher(m_och_pron.ipa(oc, oc_preview)))
			end
			insert(text, "</div>")
		end
		insert(text, "</div>")
		if namespace == "" or namespace == "-" then
			if mc then
				if is_single_hanzi then
					if mc_preview:find("k̚$") then
						insert(text, "[[Category:Middle Chinese -k characters|" .. sortkey .. "]]")
					elseif mc_preview:find("t̚$") then
						insert(text, "[[Category:Middle Chinese -t characters|" .. sortkey .. "]]")
					elseif mc_preview:find("p̚$") then
						insert(text, "[[Category:Middle Chinese -p characters|" .. sortkey .. "]]")
					end
				end
			end
			if not args["cat"] then
				insert(text, "[[Category:zh-pron usage missing POS]]")
			end
		end
	end

	local conv_text = {} --categories
	if namespace == "" or namespace == "-" then
		local catText = args["cat"] or ""
		local cat_start = "[[Category:"
		local cat_end = "]]"
		if w_rom then
			w_rom = gsub(w_rom, "%d", "")
		end
		
		local function add_cat(cat_table, name, cat)
			insert(cat_table, cat_start .. name .. cat .. "|" .. sortkey .. cat_end)
		end

		local cats = split(catText, ",", true)
		for i = 1, #cats do
			if pos_aliases_cat[cats[i]] == "chengyu" then
				insert(cats, i, "idioms")
				break
			end
		end
		insert(cats, 1, "lemmas")
		if is_single_hanzi then
			insert(cats, 2, "hanzi")
		end
		for i = 1, #cats do
			local cat = cats[i]
			if cat == "" then break end
			cat = gsub(cat, "^ +", "")
			if find(cat, ":") then
				local cat_split = split(cat, ":", true)
				local lang_name = langname_abbr[cat_split[1]]
				local category = pos_aliases_cat[cat_split[2]] or cat
				add_cat(conv_text, "Chinese ", category)
				insert(conv_text, cat_start .. lang_name .. " " .. category .. "|" .. sortkey .. cat_end)
			else
				cat = pos_aliases_cat[cat] or cat
				add_cat(conv_text, "Chinese ", cat)
				if m_rom or m_x_rom or m_nj_rom then add_cat(conv_text, "Mandarin ", cat) end
				if has_var("m-s") then add_cat(conv_text, "Sichuanese ", cat) end
				if has_var("dg") then add_cat(conv_text, "Dungan ", cat) end
				if c_rom or c_dg_rom or c_yj_rom then add_cat(conv_text, "Cantonese ", cat) end
				if c_t_rom then add_cat(conv_text, "Taishanese ", cat) end
				if has_var("g") then add_cat(conv_text, "Gan ", cat) end
				if h_rom and (find(h_rom, "pfs=.") or find(h_rom, "gd=.") or find(h_rom, "hrs=.") or find(h_rom, "ct=.")) or #h_audio > 0 then
					add_cat(conv_text, "Hakka ", cat)
				end
				if has_var("j") then add_cat(conv_text, "Jin ", cat) end
				if has_var("mb") then add_cat(conv_text, "Northern Min ", cat) end
				if has_var("md") then add_cat(conv_text, "Eastern Min ", cat) end
				if has_var("mn") then add_cat(conv_text, "Hokkien ", cat) end
				if has_var("mn-t") then add_cat(conv_text, "Teochew ", cat) end
				if has_var("mn-l") then add_cat(conv_text, "Leizhou Min ", cat) end
				if has_var("px") then add_cat(conv_text, "Puxian Min ", cat) end
				if has_var("sp") then add_cat(conv_text, "Southern Pinghua ", cat) end
				if has_var("w") then add_cat(conv_text, "Wu ", cat) end
				if has_var("w-j") then add_cat(conv_text, "Wu ", cat) end
				if has_var("x") then add_cat(conv_text, "Xiang ", cat) end
				if has_var("x-l") then add_cat(conv_text, "Xiang ", cat) end
				if has_var("x-h") then add_cat(conv_text, "Xiang ", cat) end
				if mc and has_var("mc") then
					add_cat(conv_text, "Middle Chinese ", cat)
				end
				if oc and has_var("oc") then
					add_cat(conv_text, "Old Chinese ", cat)
				end
			end
		end
		if not args.only_cat then
			insert(conv_text, cat_start .. "Chinese terms with IPA pronunciation|" .. sortkey .. cat_end)
		end
		if not args.poj_form_zh_see then
			if not find(pagename, "[" .. hanzi .. bopomofo .. "]") then
				insert(conv_text, cat_start .. "Chinese terms written in foreign scripts|" .. sortkey .. cat_end)
			end
			-- TODO: handle Zhuyin.
			-- Note: this parses any IDS to pick out the full character.
			for _, character in ipairs(explode_chars(pagename)) do
				if match(character, "[" .. hanzi .. "%%%+%-·×々〻𖿣⿰-⿿㇯]") then
					insert(conv_text, cat_start .. "Chinese terms spelled with " .. character .. "|" .. sortkey .. cat_end)
				end
			end
		end
	end

	local output = concat(text) .. concat(conv_text)
	if namespace ~= "" and namespace ~= "-" then
		output = gsub(output, "%[%[Category:[^%]]+%]%]", "")
	end
	return output
end

return export