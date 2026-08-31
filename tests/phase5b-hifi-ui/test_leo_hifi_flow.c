#include <stdio.h>
#include <stdlib.h>
#include "leo_hifi_flow.h"
static int count;
#define CHECK(x) do { count++; if (!(x)) { fprintf(stderr,"FAIL line %d\n",__LINE__); exit(1); } } while(0)
int main(void) {
    struct leo_hifi_flow f={0};
    leo_flow_reset(&f); uint64_t t=f.token;
    leo_flow_sample(&f,t,1,1024,1024,512,true,1000); CHECK(!leo_flow_live(&f,1000));
    leo_flow_sample(&f,t,1,1536,1024,512,true,1010); CHECK(!leo_flow_live(&f,1010));
    leo_flow_sample(&f,t,1,2048,1024,512,true,1020); CHECK(leo_flow_live(&f,1020));
    CHECK(leo_flow_live(&f,3020)); CHECK(!leo_flow_live(&f,3021)); CHECK(!leo_flow_live(&f,1019));
    leo_flow_sample(&f,t,1,2048,1024,512,true,1030); CHECK(!leo_flow_live(&f,1030));
    leo_flow_sample(&f,t,1,2560,1024,512,true,1040);
    leo_flow_sample(&f,t,1,3072,1024,512,true,1050); CHECK(leo_flow_live(&f,1050));
    leo_flow_sample(&f,t,1,3584,1024,2048,true,1060); CHECK(!f.valid);
    leo_flow_sample(&f,t,1,100,1024,0,true,1070); CHECK(!f.valid);
    leo_flow_sample(&f,t,1,4096,1024,512,true,1080);
    leo_flow_sample(&f,t,1,4608,1024,512,true,1090);
    leo_flow_sample(&f,t,1,5120,1024,512,true,1100); CHECK(leo_flow_live(&f,1100));
    leo_flow_reset(&f); CHECK(f.token!=t); CHECK(!leo_flow_live(&f,1100));
    leo_flow_sample(&f,t,1,6000,1024,512,true,1110); CHECK(!f.valid);
    t=f.token;
    leo_flow_sample(&f,t,2,1024,1024,512,true,1200);
    leo_flow_sample(&f,t,2,1536,1024,512,true,1210);
    leo_flow_sample(&f,t,2,2048,1024,512,true,1220); CHECK(leo_flow_live(&f,1220));
    leo_flow_sample(&f,t,3,10000,1024,512,true,1230); CHECK(!leo_flow_live(&f,1230));
    leo_flow_sample(&f,t,3,11000,1024,512,false,1240); CHECK(!f.valid);
    printf("leo_hifi_flow: %d passed\n",count); return 0;
}
