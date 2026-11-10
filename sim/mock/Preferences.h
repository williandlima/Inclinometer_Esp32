#pragma once
// Preferences (NVS) falsa: um arquivo de texto "chave valor" por namespace,
// no caminho de NVS_MOCK_FILE (sem a variável, só memória) — assim um teste
// pode "desligar e religar" o firmware rodando o binário duas vezes.
#include <cstdio>
#include <cstdlib>
#include <map>
#include <string>
class Preferences {
public:
    bool begin(const char *ns, bool readOnly = false) {
        _ns = ns;
        _data.clear();
        if (const char *p = getenv("NVS_MOCK_FILE")) {
            _path = p;
            if (FILE *f = fopen(p, "r")) {
                char k[64];
                double v;
                while (fscanf(f, "%63s %lf", k, &v) == 2) _data[k] = v;
                fclose(f);
            }
        }
        return true;
    }
    void end() {}
    bool isKey(const char *key) { return _data.count(_ns + "." + key) > 0; }
    float getFloat(const char *key, float def = 0.0f) {
        auto it = _data.find(_ns + "." + key);
        return it == _data.end() ? def : static_cast<float>(it->second);
    }
    size_t putFloat(const char *key, float value) {
        _data[_ns + "." + key] = value;
        writes()++;
        if (!_path.empty()) {
            if (FILE *f = fopen(_path.c_str(), "w")) {
                for (auto &kv : _data) fprintf(f, "%s %.9g\n", kv.first.c_str(), kv.second);
                fclose(f);
            }
        }
        return sizeof(float);
    }
    // Quantas gravações na flash o firmware fez (o teste confere o desgaste).
    static int &writes() { static int n = 0; return n; }

private:
    std::string _ns, _path;
    std::map<std::string, double> _data;
};
