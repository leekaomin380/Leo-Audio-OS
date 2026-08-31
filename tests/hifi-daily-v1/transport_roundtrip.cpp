// Links the unmodified MoKee libcutils sources named in transport/sources.json.
#include <cutils/str_parms.h>
#include <cstdlib>
#include <iostream>
#include <string>

int main() {
    std::string line;
    while (std::getline(std::cin, line)) {
        auto tab = line.find('\t');
        if (tab == std::string::npos) return 2;
        std::string original = line.substr(tab+1);
        const std::string prefix = "leo_hifi_status=";
        if (original.compare(0,prefix.size(),prefix) != 0) return 2;
        str_parms *reply = str_parms_create();
        if (!reply) return 2;
        int rc = str_parms_add_str(reply, "leo_hifi_status", original.c_str()+prefix.size());
        char *wire = str_parms_to_str(reply);
        if (rc != 0 || !wire || original != wire) return 1;
        // Exercise libcutils' actual parser as well as the actual serializer.
        str_parms *parsed = str_parms_create_str(wire);
        char *again = parsed ? str_parms_to_str(parsed) : nullptr;
        if (!again || original != again) return 1;
        std::cout << line.substr(0,tab+1) << again << '\n';
        free(again); str_parms_destroy(parsed); free(wire); str_parms_destroy(reply);
    }
}
