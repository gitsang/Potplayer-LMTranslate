/*
    LMTranslate - Real-time subtitle translation for PotPlayer
    OpenAI-compatible LLM API with YAML provider config + rolling context.

    Login dialog (two fields):
      Field 1 (Model) : {provider-id}/{model-id}   e.g. siliconflow/qwen/qwen2.5-7b
      Field 2 (Key)   : API key (leave empty if the service needs none)

    Config "SubtitleTranslate - LMTranslate.yaml" next to this script:
      context: 8            # previous subtitle pairs kept as context (0 = off)
      providers:
        siliconflow: https://api.siliconflow.cn/v1
        openai: https://api.openai.com/v1
    provider-id must NOT contain '/'.
    The model-id may contain '/' (everything after the first '/' is the model).

    Context: the last N source/translation pairs are sent as multi-turn chat
    history so names, pronouns and terminology stay consistent. The context
    is cleared automatically when the playing file changes.

    NOTE: PotPlayer's AngelScript string dialect:
      .find(sub) -> position or -1 ; .MakeLower() ; .Trim() RETURNS a new
      string (must assign) ; .substr(pos,len) ; .Left/.Right(n) ; .length()
*/

string UserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PotPlayer-LMTranslate/1.2";

// ---- configured state ----
string g_endpoint;   // full chat/completions URL
string g_model;      // model id sent to the API
string g_key;        // api key
dictionary g_providers;

// ---- rolling context ----
array<string> g_ctx_src;
array<string> g_ctx_dst;
int g_ctx_max = 8;
string g_last_file = "";

// ---- plugin info ----
string GetTitle()
{
    return "{$CP936=LMTranslate 翻译$}{$CP950=LMTranslate 翻譯$}{$CP0=LMTranslate$}";
}

string GetVersion()
{
    return "1.2.0";
}

string GetDesc()
{
    return "OpenAI-compatible LLM translation with YAML providers and rolling context.";
}

string GetLoginTitle()
{
    return "{$CP936=LMTranslate 配置$}{$CP0=LMTranslate Configuration$}";
}

string GetLoginDesc()
{
    return "{$CP936=详细配置 SubtitleTranslate - LMTranslate.yaml$}{$CP0=See SubtitleTranslate - LMTranslate.yaml for details$}";
}

string GetUserText()
{
    return "{$CP936=模型 (provider/model)：$}{$CP0=Model (provider/model):$}";
}

string GetPasswordText()
{
    return "{$CP936=API 密钥：$}{$CP0=API Key:$}";
}

// ---- lifecycle ----
void OnInitialize()
{
    // marker so we can confirm PotPlayer loaded this plugin
    uintptr f = HostFileCreate("LMTranslate_loaded.txt");
    if (f != 0)
    {
        HostFileWrite(f, "LMTranslate loaded");
        HostFileClose(f);
    }
}

void OnFinalize()
{
}

// ---- helpers ----
string JsonEsc(string s)
{
    s.replace("\\", "\\\\");
    s.replace("\"", "\\\"");
    s.replace("\n", "\\n");
    s.replace("\r", "\\r");
    s.replace("\t", "\\t");
    return s;
}

int StrToInt(string s)
{
    int v = 0;
    for (int i = 0; i < int(s.length()); i++)
    {
        string c = s.substr(i, 1);
        int d = -1;
        if (c == "0") d = 0;
        else if (c == "1") d = 1;
        else if (c == "2") d = 2;
        else if (c == "3") d = 3;
        else if (c == "4") d = 4;
        else if (c == "5") d = 5;
        else if (c == "6") d = 6;
        else if (c == "7") d = 7;
        else if (c == "8") d = 8;
        else if (c == "9") d = 9;
        if (d < 0) break;
        v = v * 10 + d;
    }
    return v;
}

string ScriptPath(const string &in name)
{
    string folder = HostGetScriptFolder();
    if (folder.length() > 0)
    {
        string last = folder.Right(1);
        if (last != "\\" && last != "/") folder = folder + "\\";
    }
    return folder + name;
}

void ClearContext()
{
    g_ctx_src.resize(0);
    g_ctx_dst.resize(0);
}

// Minimal YAML reader.
// Reads "context: N" (or "context: off") and provider mappings:
//   providers:
//     id: https://...
// Flat top-level "id: https://..." lines also work.
void LoadProviders()
{
    g_providers.deleteAll();

    uintptr fp = HostFileOpen(ScriptPath("SubtitleTranslate - LMTranslate.yaml"));
    if (fp == 0) return;

    int64 len = HostFileLength(fp);
    string content = "";
    if (len > 0) content = HostFileRead(fp, int(len));
    HostFileClose(fp);

    string rest = content;
    while (true)
    {
        int nl = rest.find("\n");
        string line;
        if (nl < 0)
        {
            line = rest;
        }
        else
        {
            line = rest.substr(0, nl);
            rest = rest.substr(nl + 1);
        }

        // strip comments
        int hc = line.find("#");
        if (hc >= 0) line = line.substr(0, hc);
        line = line.Trim();

        if (nl < 0 && line.empty()) break;
        if (!line.empty())
        {
            // split at first ':' (provider ids never contain ':')
            int colon = line.find(":");
            if (colon > 0)
            {
                string id = line.substr(0, colon).Trim();
                string val = line.substr(colon + 1).Trim();

                if (!id.empty() && !val.empty())
                {
                    string lid = id.MakeLower();
                    if (lid == "context")
                    {
                        if (val.MakeLower() == "off") g_ctx_max = 0;
                        else g_ctx_max = StrToInt(val);
                    }
                    else if (id.find("/") == -1
                        && (val.Left(7) == "http://" || val.Left(8) == "https://"))
                    {
                        g_providers.set(id, val);
                    }
                }
            }
        }

        if (nl < 0) break;
    }
}

string BuildEndpoint(string url)
{
    url = url.Trim();
    while (url.length() > 0 && url.Right(1) == "/") url = url.Left(url.length() - 1);
    if (url.MakeLower().find("chat/completions") != -1) return url;
    return url + "/chat/completions";
}

// ---- login ----
string ServerLogin(string User, string Pass)
{
    User = User.Trim();
    if (User.empty()) return "{$CP936=请填写模型，格式 provider-id/model-id$}{$CP0=Enter model as provider-id/model-id$}";

    int slash = User.find("/");
    if (slash <= 0)
        return "{$CP936=格式错误：应为 provider-id/model-id，例如 siliconflow/qwen/qwen2.5-7b$}{$CP0=Bad format: use provider-id/model-id, e.g. siliconflow/qwen/qwen2.5-7b$}";

    string provider = User.substr(0, slash).Trim();
    string model = User.substr(slash + 1).Trim();
    if (provider.empty() || model.empty())
        return "{$CP936=provider-id 与 model-id 都不能为空$}{$CP0=provider-id and model-id must not be empty$}";

    LoadProviders();
    string url;
    if (!g_providers.get(provider, url))
    {
        string avail = "";
        array<string> keys = g_providers.getKeys();
        for (int i = 0; i < int(keys.length()); i++)
        {
            if (i > 0) avail = avail + ", ";
            avail = avail + keys[i];
        }
        if (avail.empty()) avail = "{$CP936=(无，请先编辑 SubtitleTranslate - LMTranslate.yaml)$}{$CP0=(none, edit SubtitleTranslate - LMTranslate.yaml first)$}";
        return "{$CP936=未找到 provider '$}{$CP0=Unknown provider '$}" + provider + "{$CP936='。可用：$}{$CP0='. Available: $}" + avail;
    }

    g_model = model;
    g_key = Pass;
    g_endpoint = BuildEndpoint(url);
    ClearContext();
    g_last_file = "";
    return "200 ok";
}

void ServerLogout()
{
    g_endpoint = "";
    g_model = "";
    g_key = "";
    ClearContext();
    g_last_file = "";
}

// ---- languages ----
array<string> LangTable =
{
    "", "Arabic", "Bulgarian", "Catalan", "Chinese", "Croatian", "Czech",
    "Danish", "Dutch", "English", "Estonian", "Finnish", "French", "German",
    "Greek", "Hebrew", "Hindi", "Hungarian", "Indonesian", "Italian",
    "Japanese", "Korean", "Latvian", "Lithuanian", "Malay", "Norwegian",
    "Persian", "Polish", "Portuguese", "Romanian", "Russian", "Slovak",
    "Slovenian", "Spanish", "Swedish", "Thai", "Turkish", "Ukrainian",
    "Urdu", "Vietnamese"
};

array<string> GetSrcLangs()
{
    array<string> ret = LangTable;
    return ret;
}

array<string> GetDstLangs()
{
    array<string> ret = LangTable;
    ret.erase(0);
    return ret;
}

// ---- response parsing ----
string findContent(JsonValue node)
{
    if (node.isObject())
    {
        JsonValue content = node["content"];
        if (content.isString()) return content.asString();
        array<string> keys = node.getKeys();
        for (int i = 0; i < int(keys.length()); i++)
        {
            string ret = findContent(node[keys[i]]);
            if (!ret.empty()) return ret;
        }
    }
    else if (node.isArray())
    {
        for (int i = 0; i < int(node.size()); i++)
        {
            string ret = findContent(node[i]);
            if (!ret.empty()) return ret;
        }
    }
    return "";
}

string ExtractContent(JsonValue root)
{
    JsonValue choices = root["choices"];
    if (choices.isArray() && choices.size() > 0)
    {
        JsonValue first = choices[0];
        JsonValue msg = first["message"];
        JsonValue c = msg["content"];
        if (c.isString()) return c.asString();
    }
    return findContent(root);
}

// ---- translate ----
string Translate(string Text, string &in SrcLang, string &in DstLang)
{
    if (g_model.empty() || g_endpoint.empty()) return "";

    Text = Text.Trim();
    if (Text.empty()) return "";

    // new video -> drop stale context
    string curFile = HostGetPlayingFileName();
    if (curFile != g_last_file)
    {
        ClearContext();
        g_last_file = curFile;
    }

    // identical consecutive line -> reuse previous translation
    int n = int(g_ctx_src.length());
    if (n > 0 && g_ctx_src[n - 1] == Text) return g_ctx_dst[n - 1];

    string srcName = SrcLang.empty() ? "the auto-detected source language" : SrcLang;
    string system = "You are a professional subtitle translator. Translate each user message from "
                  + srcName + " into " + DstLang
                  + ". Earlier messages in this conversation are previously translated subtitle lines: "
                  + "use them only as context to keep names, pronouns, terminology and tone consistent. "
                  + "Reply with ONLY the translation of the latest message, without quotes or comments, preserving punctuation.";

    string msgs = "{\"role\":\"system\",\"content\":\"" + JsonEsc(system) + "\"}";
    if (g_ctx_max > 0)
    {
        int from = n > g_ctx_max ? n - g_ctx_max : 0;
        for (int i = from; i < n; i++)
        {
            msgs = msgs + ",{\"role\":\"user\",\"content\":\"" + JsonEsc(g_ctx_src[i]) + "\"}";
            msgs = msgs + ",{\"role\":\"assistant\",\"content\":\"" + JsonEsc(g_ctx_dst[i]) + "\"}";
        }
    }
    msgs = msgs + ",{\"role\":\"user\",\"content\":\"" + JsonEsc(Text) + "\"}";

    string post = "{\"model\":\"" + JsonEsc(g_model)
                + "\",\"messages\":[" + msgs + "],\"temperature\":0,\"stream\":false}";

    string header = "Content-Type: application/json\r\naccept: application/json\r\n";
    if (!g_key.empty()) header = header + "Authorization: Bearer " + g_key + "\r\n";

    string ret = "";
    uintptr http = HostOpenHTTP(g_endpoint, UserAgent, header, post);
    if (http != 0)
    {
        string json = HostGetContentHTTP(http);
        JsonReader Reader;
        JsonValue Root;
        if (Reader.parse(json, Root) && Root.isObject())
        {
            ret = ExtractContent(Root);
            if (!ret.empty())
            {
                ret.replace("<br/>", "\n");
                ret.replace("<br />", "\n");
                ret.replace("<br  />", "\n");
                ret.replace("\n\n", "\n");
                ret = ret.Trim();
                ret = HostRegExpRemove(ret, "^(Here is|Here's) [a-zA-Z ,]+:");

                if (g_ctx_max > 0 && !ret.empty())
                {
                    g_ctx_src.insertLast(Text);
                    g_ctx_dst.insertLast(ret);
                    while (int(g_ctx_src.length()) > g_ctx_max)
                    {
                        g_ctx_src.erase(0);
                        g_ctx_dst.erase(0);
                    }
                }

                SrcLang = "UTF8";
                DstLang = "UTF8";
            }
        }
        HostCloseHTTP(http);
    }
    return ret;
}