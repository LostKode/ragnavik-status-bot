using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using BepInEx;
using HarmonyLib;
using UnityEngine;

namespace RagnavikProgress;

[BepInPlugin("lostkode.ragnavik.progress", "Ragnavik Progress", "1.0.1")]
public sealed class RagnavikProgressPlugin : BaseUnityPlugin
{
    private readonly FieldInfo? _globalKeysField = AccessTools.Field(typeof(ZoneSystem), "m_globalKeys");
    private float _nextCheck;
    private float _nextHeartbeat;
    private string _lastKeys = "";
    private string _reportKeys = "";
    private Task<bool>? _reportTask;

    private void Update()
    {
        if (_reportTask is { IsCompleted: true })
        {
            try
            {
                if (_reportTask.GetAwaiter().GetResult())
                {
                    _lastKeys = _reportKeys;
                    _nextHeartbeat = Time.realtimeSinceStartup + 3600f;
                }
                else
                {
                    Logger.LogWarning("Boss progress report returned an unexpected HTTP status.");
                    _nextCheck = Time.realtimeSinceStartup + 300f;
                }
            }
            catch (Exception exception)
            {
                Logger.LogWarning($"Boss progress report failed: {exception.Message}");
                _nextCheck = Time.realtimeSinceStartup + 300f;
            }
            _reportTask = null;
        }

        if (Time.realtimeSinceStartup < _nextCheck)
            return;
        _nextCheck = Time.realtimeSinceStartup + 60f;
        if (ZNet.instance == null || !ZNet.instance.IsServer() || ZoneSystem.instance == null)
            return;
        if (_globalKeysField == null)
        {
            Logger.LogWarning("ZoneSystem.m_globalKeys is unavailable; boss progress cannot be reported.");
            return;
        }
        var allKeys = _globalKeysField.GetValue(ZoneSystem.instance) as HashSet<string>;
        if (allKeys == null)
            return;
        var defeated = allKeys.Where(key => key.StartsWith("defeated_", StringComparison.OrdinalIgnoreCase))
            .OrderBy(key => key, StringComparer.OrdinalIgnoreCase).ToArray();
        var signature = string.Join("|", defeated);
        if (_reportTask != null || (signature == _lastKeys && Time.realtimeSinceStartup < _nextHeartbeat))
            return;

        string token;
        try
        {
            token = File.ReadAllText("/run/secrets/ragnavik_status_hook_token").Trim();
        }
        catch (Exception exception)
        {
            Logger.LogWarning($"Boss progress hook token unavailable: {exception.Message}");
            _nextCheck = Time.realtimeSinceStartup + 600f;
            return;
        }
        var body = JsonUtility.ToJson(new BossReport
        {
            container = Environment.GetEnvironmentVariable("HOSTNAME") ?? "",
            keys = defeated,
        });
        _reportKeys = signature;
        _reportTask = Task.Run(() => SendReport(body, token));
    }

    private static bool SendReport(string body, string token)
    {
        var bytes = Encoding.UTF8.GetBytes(body);
        var request = (HttpWebRequest)WebRequest.Create("http://192.168.86.21:8787/bosses");
        request.Method = "POST";
        request.ContentType = "application/json";
        request.Headers["X-Ragnavik-Token"] = token;
        request.Timeout = 3000;
        request.ReadWriteTimeout = 3000;
        request.ContentLength = bytes.Length;
        using (var stream = request.GetRequestStream())
            stream.Write(bytes, 0, bytes.Length);
        using var response = (HttpWebResponse)request.GetResponse();
        return response.StatusCode == HttpStatusCode.NoContent;
    }

    [Serializable]
    private sealed class BossReport
    {
        public string container = "";
        public string[] keys = Array.Empty<string>();
    }
}
