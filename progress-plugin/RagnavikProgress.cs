using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using BepInEx;
using BepInEx.Configuration;
using HarmonyLib;
using UnityEngine;

namespace RagnavikProgress;

[BepInPlugin("lostkode.ragnavik.progress", "Ragnavik Progress", "1.1.0")]
public sealed class RagnavikProgressPlugin : BaseUnityPlugin
{
    private static RagnavikProgressPlugin? _instance;
    private readonly FieldInfo? _globalKeysField = AccessTools.Field(typeof(ZoneSystem), "m_globalKeys");
    private ConfigEntry<bool>? _enabled;
    private ConfigEntry<string>? _endpoint;
    private ConfigEntry<string>? _tokenFile;
    private ConfigEntry<string>? _tokenHeader;
    private ConfigEntry<string>? _serverName;
    private ConfigEntry<int>? _checkSeconds;
    private ConfigEntry<int>? _heartbeatSeconds;
    private ConfigEntry<int>? _milestoneStep;
    private ConfigEntry<float>? _participantRadius;
    private ConfigEntry<bool>? _reportBosses;
    private ConfigEntry<bool>? _reportLevels;
    private float _nextCheck;
    private float _nextHeartbeat;
    private string _lastSignature = "";
    private string _reportSignature = "";
    private Task<bool>? _reportTask;
    private readonly List<BossKill> _pendingBossKills = new();
    private readonly HashSet<string> _seenBossDeaths = new(StringComparer.Ordinal);
    private string[] _reportedBossKillIds = Array.Empty<string>();

    private void Awake()
    {
        _instance = this;
        _enabled = Config.Bind("General", "Enabled", false,
            "Enable reporting after a private server endpoint is configured.");
        _endpoint = Config.Bind("Connection", "Endpoint", "",
            "Private HTTP endpoint that accepts progress reports.");
        _tokenFile = Config.Bind("Connection", "TokenFile", "",
            "Server-only path containing the authentication token.");
        _tokenHeader = Config.Bind("Connection", "TokenHeader", "X-Progress-Token",
            "HTTP header used to send the token.");
        _serverName = Config.Bind("Messages", "ServerName", "Valheim",
            "Server name included in progress reports.");
        _milestoneStep = Config.Bind("Milestones", "EpicMMOLevelStep", 10,
            new ConfigDescription("Report EpicMMO player levels in this interval.",
                new AcceptableValueRange<int>(1, 100)));
        _reportBosses = Config.Bind("Milestones", "ReportBossDefeats", true,
            "Report boss defeats, killing player, and nearby participants.");
        _reportLevels = Config.Bind("Milestones", "ReportEpicMMOLevels", true,
            "Report connected characters reaching EpicMMO level milestones.");
        _participantRadius = Config.Bind("Milestones", "BossParticipantRadius", 100f,
            new ConfigDescription("Meters from a defeated boss counted as participating players.",
                new AcceptableValueRange<float>(1f, 500f)));
        _checkSeconds = Config.Bind("Timing", "CheckSeconds", 30,
            new ConfigDescription("Seconds between progress checks.",
                new AcceptableValueRange<int>(10, 600)));
        _heartbeatSeconds = Config.Bind("Timing", "HeartbeatSeconds", 3600,
            new ConfigDescription("Seconds between unchanged state reports.",
                new AcceptableValueRange<int>(300, 86400)));
        Harmony.CreateAndPatchAll(typeof(RagnavikProgressPlugin));
    }

    private void Update()
    {
        if (_reportTask is { IsCompleted: true })
        {
            try
            {
                if (_reportTask.GetAwaiter().GetResult())
                {
                    _lastSignature = _reportSignature;
                    _nextHeartbeat = Time.realtimeSinceStartup + _heartbeatSeconds!.Value;
                    _pendingBossKills.RemoveAll(kill => _reportedBossKillIds.Contains(kill.id));
                }
                else
                {
                    Logger.LogWarning("Progress report returned an unexpected HTTP status.");
                    _nextCheck = Time.realtimeSinceStartup + 300f;
                }
            }
            catch (Exception exception)
            {
                Logger.LogWarning($"Progress report failed: {exception.Message}");
                _nextCheck = Time.realtimeSinceStartup + 300f;
            }
            _reportTask = null;
        }

        if (_enabled?.Value != true || string.IsNullOrWhiteSpace(_endpoint?.Value) ||
            Time.realtimeSinceStartup < _nextCheck)
            return;
        _nextCheck = Time.realtimeSinceStartup + _checkSeconds!.Value;
        if (ZNet.instance == null || !ZNet.instance.IsServer() || ZoneSystem.instance == null)
            return;
        if (_globalKeysField == null)
        {
            Logger.LogWarning("ZoneSystem.m_globalKeys is unavailable; progress cannot be reported.");
            return;
        }

        var allKeys = _globalKeysField.GetValue(ZoneSystem.instance) as HashSet<string>;
        if (allKeys == null)
            return;
        var bosses = _reportBosses!.Value
            ? allKeys.Where(key => key.StartsWith("defeated_", StringComparison.OrdinalIgnoreCase))
                .OrderBy(key => key, StringComparer.OrdinalIgnoreCase).ToArray()
            : Array.Empty<string>();
        var players = _reportLevels!.Value ? ReadPlayers() : Array.Empty<PlayerProgress>();
        var signature = string.Join("|", bosses) + "#" + string.Join("|",
            players.Select(player => $"{player.id}:{player.level}")) + "#" +
            string.Join("|", _pendingBossKills.Select(kill => kill.id));
        if (_reportTask != null || (signature == _lastSignature &&
            Time.realtimeSinceStartup < _nextHeartbeat))
            return;

        string token;
        try
        {
            token = string.IsNullOrWhiteSpace(_tokenFile?.Value)
                ? "" : File.ReadAllText(_tokenFile.Value).Trim();
        }
        catch (Exception exception)
        {
            Logger.LogWarning($"Progress token unavailable: {exception.Message}");
            _nextCheck = Time.realtimeSinceStartup + 600f;
            return;
        }

        var body = JsonUtility.ToJson(new ProgressReport
        {
            server = _serverName!.Value,
            instance = Environment.GetEnvironmentVariable("HOSTNAME") ?? "",
            bosses = bosses,
            players = players,
            bossKills = _pendingBossKills.ToArray(),
            milestoneStep = _milestoneStep!.Value,
        });
        _reportedBossKillIds = _pendingBossKills.Select(kill => kill.id).ToArray();
        _reportSignature = signature;
        _reportTask = Task.Run(() => SendReport(body, token));
    }

    [HarmonyPatch(typeof(Character), "RPC_Damage")]
    [HarmonyPostfix]
    private static void AfterCharacterDamage(Character __instance, HitData hit)
    {
        if (_instance == null || _instance._reportBosses?.Value != true ||
            __instance == null || hit == null ||
            !__instance.IsBoss() || __instance.GetHealth() > 0f)
            return;
        var zdo = __instance.GetComponent<ZNetView>()?.GetZDO();
        var eventId = zdo?.m_uid.ToString() ?? $"{__instance.name}:{Time.frameCount}";
        if (!_instance._seenBossDeaths.Add(eventId))
            return;

        var nearby = Player.GetAllPlayers()
            .Where(player => player != null && !player.IsDead() &&
                Vector3.Distance(player.transform.position, __instance.transform.position) <=
                _instance._participantRadius!.Value)
            .Select(player => player.GetPlayerName())
            .Where(name => !string.IsNullOrWhiteSpace(name))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderBy(name => name, StringComparer.OrdinalIgnoreCase)
            .ToArray();
        var killer = hit.GetAttacker() is Player playerKiller
            ? playerKiller.GetPlayerName() : "Unknown Viking";
        _instance._pendingBossKills.Add(new BossKill
        {
            id = eventId,
            key = __instance.m_defeatSetGlobalKey ?? "",
            boss = __instance.GetHoverName(),
            killer = killer,
            participants = nearby,
        });
        _instance._nextCheck = 0f;
    }

    private PlayerProgress[] ReadPlayers()
    {
        if (ZDOMan.instance == null)
            return Array.Empty<PlayerProgress>();
        var result = new List<PlayerProgress>();
        foreach (var player in ZNet.instance.GetPlayerList())
        {
            var zdo = ZDOMan.instance.GetZDO(player.m_characterID);
            if (zdo == null)
                continue;
            result.Add(new PlayerProgress
            {
                id = player.m_characterID.UserID.ToString(),
                name = player.m_name ?? "Unknown Viking",
                level = Math.Max(1, zdo.GetInt("EpicMMOSystem_level", 1)),
            });
        }
        return result.OrderBy(player => player.id, StringComparer.Ordinal).ToArray();
    }

    private bool SendReport(string body, string token)
    {
        var bytes = Encoding.UTF8.GetBytes(body);
        var request = (HttpWebRequest)WebRequest.Create(_endpoint!.Value);
        request.Method = "POST";
        request.ContentType = "application/json";
        if (!string.IsNullOrWhiteSpace(token))
            request.Headers[_tokenHeader!.Value] = token;
        request.Timeout = 3000;
        request.ReadWriteTimeout = 3000;
        request.ContentLength = bytes.Length;
        using (var stream = request.GetRequestStream())
            stream.Write(bytes, 0, bytes.Length);
        using var response = (HttpWebResponse)request.GetResponse();
        return response.StatusCode == HttpStatusCode.NoContent;
    }

    [Serializable]
    private sealed class ProgressReport
    {
        public string server = "";
        public string instance = "";
        public string[] bosses = Array.Empty<string>();
        public PlayerProgress[] players = Array.Empty<PlayerProgress>();
        public BossKill[] bossKills = Array.Empty<BossKill>();
        public int milestoneStep = 10;
    }

    [Serializable]
    private sealed class PlayerProgress
    {
        public string id = "";
        public string name = "";
        public int level;
    }

    [Serializable]
    private sealed class BossKill
    {
        public string id = "";
        public string key = "";
        public string boss = "";
        public string killer = "";
        public string[] participants = Array.Empty<string>();
    }
}
