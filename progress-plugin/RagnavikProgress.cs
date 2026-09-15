using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using BepInEx;
using HarmonyLib;
using UnityEngine;
using UnityEngine.Networking;

namespace RagnavikProgress;

[BepInPlugin("lostkode.ragnavik.progress", "Ragnavik Progress", "1.0.0")]
public sealed class RagnavikProgressPlugin : BaseUnityPlugin
{
    private readonly FieldInfo? _globalKeysField = AccessTools.Field(typeof(ZoneSystem), "m_globalKeys");
    private float _nextCheck;
    private float _nextHeartbeat;
    private string _lastKeys = "";
    private bool _sending;

    private void Update()
    {
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
        if (!_sending && (signature != _lastKeys || Time.realtimeSinceStartup >= _nextHeartbeat))
            StartCoroutine(Report(defeated, signature));
    }

    private IEnumerator Report(string[] keys, string signature)
    {
        _sending = true;
        string token;
        try
        {
            token = File.ReadAllText("/run/secrets/ragnavik_status_hook_token").Trim();
        }
        catch (Exception exception)
        {
            Logger.LogWarning($"Boss progress hook token unavailable: {exception.Message}");
            _nextCheck = Time.realtimeSinceStartup + 600f;
            _sending = false;
            yield break;
        }
        var body = JsonUtility.ToJson(new BossReport
        {
            container = Environment.GetEnvironmentVariable("HOSTNAME") ?? "",
            keys = keys,
        });
        using var request = new UnityWebRequest("http://192.168.86.21:8787/bosses", "POST");
        request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
        request.downloadHandler = new DownloadHandlerBuffer();
        request.SetRequestHeader("Content-Type", "application/json");
        request.SetRequestHeader("X-Ragnavik-Token", token);
        request.timeout = 3;
        yield return request.SendWebRequest();
        if (request.result == UnityWebRequest.Result.Success)
        {
            _lastKeys = signature;
            _nextHeartbeat = Time.realtimeSinceStartup + 3600f;
        }
        else
        {
            Logger.LogWarning($"Boss progress report failed: {request.error}");
            _nextCheck = Time.realtimeSinceStartup + 300f;
        }
        _sending = false;
    }

    [Serializable]
    private sealed class BossReport
    {
        public string container = "";
        public string[] keys = Array.Empty<string>();
    }
}
