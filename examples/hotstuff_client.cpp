/**
 * Copyright 2018 VMware
 * Copyright 2018 Ted Yin
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <cassert>
#include <random>
#include <memory>
#include <algorithm>
#include <vector>
#include <signal.h>
#include <sys/time.h>

#include "salticidae/type.h"
#include "salticidae/netaddr.h"
#include "salticidae/network.h"
#include "salticidae/util.h"

#include "hotstuff/util.h"
#include "hotstuff/type.h"
#include "hotstuff/client.h"
#include "small_bank.h"

#define HOTSTUFF_ENABLE_BENCHMARK

using salticidae::Config;

using hotstuff::ReplicaID;
using hotstuff::NetAddr;
using hotstuff::EventContext;
using hotstuff::MsgReqCmd;
using hotstuff::MsgRespCmd;
using hotstuff::CommandDummy;
using hotstuff::HotStuffError;
using hotstuff::uint256_t;
using hotstuff::opcode_t;
using hotstuff::command_t;

EventContext ec;
ReplicaID proposer;
size_t max_async_num;
int max_iter_num;
uint32_t cid;
uint32_t cnt = 0;
uint32_t nfaulty;

struct Request {
    command_t cmd;
    size_t confirmed;
    salticidae::ElapsedTime et;
    Request(const command_t &cmd): cmd(cmd), confirmed(0) { et.start(); }
};

using Net = salticidae::MsgNetwork<opcode_t>;

std::unordered_map<ReplicaID, Net::conn_t> conns;
std::unordered_map<const uint256_t, Request> waiting;
std::vector<NetAddr> replicas;
std::vector<std::pair<struct timeval, double>> elapsed;
std::unique_ptr<Net> mn;
SmallBankManager *small_bank_manager;

void connect_all() {
    for (size_t i = 0; i < replicas.size(); i++)
        conns.insert(std::make_pair(i, mn->connect_sync(replicas[i])));
}

bool try_send(bool check = true) {
    if ((!check || waiting.size() < max_async_num) && max_iter_num)
    {
        // auto cmd = new CommandDummy(cid, cnt++);

        auto next_tx = small_bank_manager->get_next_transaction_serialized();
        auto cmd = new CommandDummy(cid, cnt++, next_tx);
        MsgReqCmd msg(*cmd);
        for (auto &p: conns) mn->send_msg(msg, p.second);
#ifndef HOTSTUFF_ENABLE_BENCHMARK

        std::string data = "";
        const uint64_t *payload =  cmd->get_payload();
        for(int i=0; i<cmd->get_payload_size(); i++){
            data += std::to_string(payload[i]) + " ";
        } 

        HOTSTUFF_LOG_INFO("send new cmd %.10s with payload (size %ld) %s",
                            get_hex(cmd->get_hash()).c_str(), cmd->get_payload_size(), data.c_str());

        
#endif
        waiting.insert(std::make_pair(
            cmd->get_hash(), Request(cmd)));
        if (max_iter_num > 0)
            max_iter_num--;

        return true;
    }
    return false;
}

void client_resp_cmd_handler(MsgRespCmd &&msg, const Net::conn_t &) {
    auto &fin = msg.fin;
    HOTSTUFF_LOG_DEBUG("got %s", std::string(msg.fin).c_str());
    const uint256_t &cmd_hash = fin.cmd_hash;
    auto it = waiting.find(cmd_hash);
    /* Guard BEFORE dereferencing. The previous ordering read it->second
       on an end() iterator, which happens routinely: the client
       broadcasts to all N replicas but erases after f+1 acks, so the
       remaining acks arrive for a hash no longer in `waiting`. */
    if (it == waiting.end()) return;
    /* Only a committed response confirms. src/hotstuff.cpp sends a
       Finality with decision=0 ("already pending, don't resend") when a
       command hash is submitted twice -- that is a receipt, not a
       commit, and counting it lets a command be "confirmed" without ever
       reaching consensus. */
    if (fin.decision != 1) return;
    auto &et = it->second.et;
    et.stop();
    if (++it->second.confirmed <= nfaulty) return; // wait for f + 1 ack
#ifndef HOTSTUFF_ENABLE_BENCHMARK
    HOTSTUFF_LOG_INFO("got %s, wall: %.3f, cpu: %.3f",
                        std::string(fin).c_str(),
                        et.elapsed_sec, et.cpu_elapsed_sec);
#else
    struct timeval tv;
    gettimeofday(&tv, nullptr);
    elapsed.push_back(std::make_pair(tv, et.elapsed_sec));
#endif
    waiting.erase(it);
    while (try_send());
}

std::pair<std::string, std::string> split_ip_port_cport(const std::string &s) {
    auto ret = salticidae::trim_all(salticidae::split(s, ";"));
    return std::make_pair(ret[0], ret[1]);
}

int main(int argc, char **argv) {
    // small_bank_manager = new SmallBankManager(10, 0.8, 0.5);

    Config config("hotstuff.conf");

    auto opt_sb_users = Config::OptValInt::create(10);
    auto opt_sb_prob_choose_mtx = Config::OptValDouble::create(0.9);
    auto opt_sb_skew_factor = Config::OptValDouble::create(0.1);
    auto opt_idx = Config::OptValInt::create(0);
    auto opt_replicas = Config::OptValStrVec::create();
    auto opt_max_iter_num = Config::OptValInt::create(100);
    auto opt_max_async_num = Config::OptValInt::create(10);
    auto opt_cid = Config::OptValInt::create(-1);
    auto opt_max_cli_msg = Config::OptValInt::create(65536); // 64K by default

    auto shutdown = [&](int) { ec.stop(); };
    salticidae::SigEvent ev_sigint(ec, shutdown);
    salticidae::SigEvent ev_sigterm(ec, shutdown);
    ev_sigint.add(SIGINT);
    ev_sigterm.add(SIGTERM);

    mn = std::make_unique<Net>(ec, Net::Config().max_msg_size(opt_max_cli_msg->get()));
    mn->reg_handler(client_resp_cmd_handler);
    mn->start();


    config.add_opt("sb-users", opt_sb_users, Config::SET_VAL);
    config.add_opt("sb-prob-choose_mtx", opt_sb_prob_choose_mtx, Config::SET_VAL);
    config.add_opt("sb-skew-factor", opt_sb_skew_factor, Config::SET_VAL);
    config.add_opt("idx", opt_idx, Config::SET_VAL);
    config.add_opt("cid", opt_cid, Config::SET_VAL);
    config.add_opt("replica", opt_replicas, Config::APPEND);
    config.add_opt("iter", opt_max_iter_num, Config::SET_VAL);
    config.add_opt("max-async", opt_max_async_num, Config::SET_VAL);
    config.add_opt("max-cli-msg", opt_max_cli_msg, Config::SET_VAL, 'S', "the maximum client message size");
    config.parse(argc, argv);
    auto idx = opt_idx->get();
    max_iter_num = opt_max_iter_num->get();
    max_async_num = opt_max_async_num->get();
    std::vector<std::string> raw;
    for (const auto &s: opt_replicas->get())
    {
        auto res = salticidae::trim_all(salticidae::split(s, ","));
        if (res.size() < 1)
            throw HotStuffError("format error");
        raw.push_back(res[0]);
    }

    if (!(0 <= idx && (size_t)idx < raw.size() && raw.size() > 0))
        throw std::invalid_argument("out of range");
    cid = opt_cid->get() != -1 ? opt_cid->get() : idx;
    for (const auto &p: raw)
    {
        auto _p = split_ip_port_cport(p);
        size_t _;
        replicas.push_back(NetAddr(NetAddr(_p.first).ip, htons(stoi(_p.second, &_))));
    }

    nfaulty = (replicas.size() - 1) / 3;
    HOTSTUFF_LOG_INFO("nfaulty = %zu", nfaulty);

    HOTSTUFF_LOG_INFO("opt_sb_users = %ld, opt_sb_prob_choose_mtx = %f, opt_sb_skew_factor = %f", opt_sb_users->get(), opt_sb_prob_choose_mtx->get(), opt_sb_skew_factor->get());
    small_bank_manager = new SmallBankManager(opt_sb_users->get(), opt_sb_prob_choose_mtx->get(), opt_sb_skew_factor->get());

    connect_all();
    while (try_send());
    ec.dispatch();

#ifdef HOTSTUFF_ENABLE_BENCHMARK
    /* Summary FIRST, then flushed. The per-record dump below is a
       localtime+strftime+fprintf per sample and loses its race with the
       harness's SIGKILL grace period on any fast run -- it was silently
       truncating at ~416k records (~21.6MB) regardless of workload,
       which made n_committed a prefix and tps a rate over only the first
       few seconds. These aggregates are O(n) and always survive. */
    if (!elapsed.empty())
    {
        double first = elapsed.front().first.tv_sec +
                       elapsed.front().first.tv_usec * 1e-6;
        double last  = elapsed.back().first.tv_sec +
                       elapsed.back().first.tv_usec * 1e-6;
        double window = last - first;
        double sum = 0;
        std::vector<double> lat;
        lat.reserve(elapsed.size());
        for (const auto &e: elapsed) { sum += e.second; lat.push_back(e.second); }
        /* nth_element is O(n) and leaves a valid permutation of the same
           multiset, so successive calls stay correct. */
        auto pct = [&lat](double q) {
            size_t k = (size_t)(q * (lat.size() - 1));
            std::nth_element(lat.begin(), lat.begin() + k, lat.end());
            return lat[k];
        };
        double p50 = pct(0.50), p95 = pct(0.95), p99 = pct(0.99);
        double mx = *std::max_element(lat.begin(), lat.end());
        fprintf(stderr,
                "[hotstuff summary] n=%zu window=%.6f mean=%.6f "
                "p50=%.6f p95=%.6f p99=%.6f max=%.6f\n",
                elapsed.size(), window, sum / elapsed.size(),
                p50, p95, p99, mx);
        fflush(stderr);
    }
    for (const auto &e: elapsed)
    {
        char fmt[64];
        struct tm *tmp = localtime(&e.first.tv_sec);
        strftime(fmt, sizeof fmt, "%Y-%m-%d %H:%M:%S.%%06u [hotstuff info] %%.6f\n", tmp);
        fprintf(stderr, fmt, e.first.tv_usec, e.second);
    }
#endif
    return 0;
}
